"""The real engines behind the multimodal ports, and the factories the daemon uses.

Every heavy package is imported lazily inside the engine, on the worker thread, so
importing this module costs nothing and the default test suite never loads a model.

- Vision: llama-cpp-python (already Pillar 1's runtime) with Moondream2, LLaVA or MTMD.
- Speech to text: faster-whisper (CTranslate2). A placeholder until installed.
- Text to speech: Piper (piper-tts, onnxruntime).
- Speaker: sounddevice (Windows, where the daemon and its microphone live).
"""

import base64
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from zeno.config import Settings
from zeno.multimodal.base import (
    Audio,
    AudioSink,
    EngineUnavailableError,
    SttEngine,
    Transcript,
    TtsEngine,
    VisionEngine,
)

log = logging.getLogger(__name__)


class LlamaVisionEngine:
    """A vision-language model on llama-cpp-python's multimodal chat handlers."""

    def __init__(self, settings: Settings) -> None:
        if settings.vision_model_path is None or settings.vision_mmproj_path is None:
            raise EngineUnavailableError(
                "No vision model configured. Set ZENO_VISION_MODEL_PATH and "
                "ZENO_VISION_MMPROJ_PATH (run setup with -Vision to fetch Moondream2)."
            )
        for path in (settings.vision_model_path, settings.vision_mmproj_path):
            if not path.is_file():
                raise EngineUnavailableError(f"Vision model file not found: {path}")
        from llama_cpp import Llama
        from llama_cpp import llama_chat_format as formats

        handlers = {
            "moondream": formats.MoondreamChatHandler,
            "llava": formats.Llava15ChatHandler,
            "mtmd": formats.MTMDChatHandler,
        }
        handler = handlers[settings.vision_handler](
            clip_model_path=str(settings.vision_mmproj_path), verbose=False
        )
        self._llama = Llama(
            model_path=str(settings.vision_model_path),
            chat_handler=handler,
            n_ctx=settings.vision_context_size,
            n_gpu_layers=settings.gpu_layers,
            n_threads=settings.threads,
            verbose=False,
        )

    def describe(self, image: bytes, mime: str, question: str, *, max_tokens: int) -> str:
        uri = f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"
        # llama-cpp-python's completion result is an untyped dict.
        result: Any = self._llama.create_chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": uri}},
                        {"type": "text", "text": question},
                    ],
                }
            ],
            max_tokens=max_tokens,
            temperature=0.1,
        )
        return str(result["choices"][0]["message"]["content"] or "").strip()

    def close(self) -> None:
        self._llama.close()


class FasterWhisperStt:
    """Speech to text with faster-whisper (CTranslate2, no PyTorch)."""

    def __init__(self, settings: Settings) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise EngineUnavailableError(
                "faster-whisper is not installed: pip install -r requirements-voice-extra.txt"
            ) from error
        self._model = WhisperModel(
            settings.stt_model, device=settings.stt_device, compute_type=settings.stt_compute_type
        )

    def transcribe(self, pcm: bytes, sample_rate: int) -> Transcript:
        import math

        import numpy as np

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments, info = self._model.transcribe(audio, beam_size=1, vad_filter=False)
        parts = list(segments)
        text = " ".join(s.text.strip() for s in parts).strip()
        confidence = sum(math.exp(s.avg_logprob) for s in parts) / len(parts) if parts else 0.0
        return Transcript(text, str(info.language or "en"), min(max(confidence, 0.0), 1.0))

    def close(self) -> None:
        del self._model


class PiperTts:
    """Text to speech with a Piper voice (.onnx plus its .onnx.json)."""

    def __init__(self, settings: Settings) -> None:
        if settings.tts_voice_path is None or not settings.tts_voice_path.is_file():
            raise EngineUnavailableError(
                "No Piper voice configured. Set ZENO_TTS_VOICE_PATH to a voice .onnx file."
            )
        from piper import PiperVoice

        self._voice = PiperVoice.load(settings.tts_voice_path)

    def synthesize(self, text: str) -> Audio:
        pcm = bytearray()
        rate = 22050
        for chunk in self._voice.synthesize(text):
            rate = chunk.sample_rate
            pcm += chunk.audio_int16_bytes
        return Audio(bytes(pcm), rate)

    def close(self) -> None:
        del self._voice


class SoundDeviceSink:
    """Plays PCM on the default output device, in short blocks so ``stop`` is quick."""

    BLOCK_SECONDS = 0.05

    def __init__(self) -> None:
        self._stop = threading.Event()

    def play(self, audio: Audio) -> None:
        import sounddevice

        self._stop.clear()
        block = int(audio.sample_rate * self.BLOCK_SECONDS) * 2
        with sounddevice.RawOutputStream(
            samplerate=audio.sample_rate, channels=1, dtype="int16"
        ) as stream:
            for start in range(0, len(audio.pcm), block):
                if self._stop.is_set():
                    stream.abort()
                    return
                stream.write(audio.pcm[start : start + block])

    def stop(self) -> None:
        self._stop.set()


def voice_missing(settings: Settings) -> str | None:
    """Why voice can't run on this machine yet, or None if it can.

    Real imports (no importlib, which the safety test bans): they run once at boot,
    and only when voice is switched on."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return "faster-whisper is not installed (pip install -r requirements-voice-extra.txt)"
    try:
        import piper  # noqa: F401
    except ImportError:
        return "piper-tts is not installed"
    if settings.tts_voice_path is None or not settings.tts_voice_path.is_file():
        return "no Piper voice is configured (set ZENO_TTS_VOICE_PATH)"
    try:
        import sounddevice  # noqa: F401
    except (ImportError, OSError):  # OSError: no PortAudio library on this machine
        return "sounddevice is not available, so there is no speaker"
    return None


def vision_missing(settings: Settings) -> str | None:
    """Why vision can't run yet, or None if it can."""
    if settings.vision_model_path is None or settings.vision_mmproj_path is None:
        return "no vision model is configured (ZENO_VISION_MODEL_PATH, ZENO_VISION_MMPROJ_PATH)"
    return None


def _no_problem(_: Settings) -> str | None:
    return None


@dataclass(frozen=True)
class MultimodalFactories:
    """How the daemon builds each engine; tests swap in fakes."""

    vision: Callable[[Settings], VisionEngine]
    stt: Callable[[Settings], SttEngine]
    tts: Callable[[Settings], TtsEngine]
    sink: Callable[[Settings], AudioSink]
    voice_missing: Callable[[Settings], str | None] = field(default=_no_problem)
    vision_missing: Callable[[Settings], str | None] = field(default=_no_problem)


def default_factories() -> MultimodalFactories:
    return MultimodalFactories(
        vision=LlamaVisionEngine,
        stt=FasterWhisperStt,
        tts=PiperTts,
        sink=lambda _: SoundDeviceSink(),
        voice_missing=voice_missing,
        vision_missing=vision_missing,
    )
