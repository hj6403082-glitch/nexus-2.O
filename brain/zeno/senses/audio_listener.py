"""Local wake-word listening ("Hey Zeno") on its own thread.

A plain ``threading.Thread`` reads microphone frames and scores each with an
openwakeword model. It never touches the asyncio loop or the EventBus directly:
on a detection it calls ``loop.call_soon_threadsafe`` to hand a ``"wake"`` event
to the loop, which is the only safe bridge from a foreign thread into asyncio and
does not block. So a slow or stuck microphone read can never stall the EventBus.

After a detection, when a ``capture_sink`` is wired, the thread switches to
CAPTURING: every following microphone frame is handed to the loop (again via
``call_soon_threadsafe``) as an ``AudioChunk`` for the voice worker, until a voice
activity detector hears the speaker stop, nothing is said, or the length cap hits.
The wake model is not scored while capturing. Then it goes back to LISTENING.

sounddevice, openwakeword and webrtcvad are imported lazily (optional), and the audio
stream, the detector and the VAD are injected, so every test runs with fakes on any
OS and never opens a real microphone.
"""

import asyncio
import logging
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from zeno.multimodal.queues import AudioChunk, EndReason
from zeno.senses.events import DeviceEvent, EventBus

log = logging.getLogger(__name__)

DEVICE = "microphone"
FRAME_SAMPLES = 1280  # openwakeword wants 80 ms of 16 kHz mono 16-bit audio
SAMPLE_RATE = 16000
VAD_FRAME_MS = 20  # webrtcvad takes 10, 20 or 30 ms frames


class AudioStream(Protocol):
    def read(self, frames: int) -> bytes: ...

    def close(self) -> None: ...


class Detector(Protocol):
    def predict(self, frame: bytes) -> Mapping[str, float]: ...


class Vad(Protocol):
    def is_speech(self, frame: bytes, sample_rate: int) -> bool: ...


StreamFactory = Callable[[], AudioStream]
DetectorFactory = Callable[[], Detector]
CaptureSink = Callable[[AudioChunk], object]
"""Receives each captured chunk on the loop thread (the voice queue's offer_audio)."""


@dataclass
class _Capture:
    utterance_id: str
    seq: int = 0
    elapsed: float = 0.0
    silence: float = 0.0
    heard_speech: bool = False


class WakeWordListener:
    """Runs the microphone scan on a background thread; publishes ``wake`` events."""

    def __init__(
        self,
        bus: EventBus,
        *,
        detector_factory: DetectorFactory,
        stream_factory: StreamFactory,
        threshold: float = 0.6,
        refractory: float = 2.0,
        frame_samples: int = FRAME_SAMPLES,
        clock: Callable[[], float] = time.monotonic,
        capture_sink: CaptureSink | None = None,
        vad: Vad | None = None,
        silence_ms: int = 800,
        no_speech_s: float = 5.0,
        max_utterance_s: float = 15.0,
    ) -> None:
        self._bus = bus
        self._detector_factory = detector_factory
        self._stream_factory = stream_factory
        self._threshold = threshold
        self._refractory = refractory
        self._frame_samples = frame_samples
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_fire = float("-inf")
        self._capture_sink = capture_sink
        self._vad = vad
        """None means every captured frame counts as speech (ends at the length cap)."""
        self._silence_s = silence_ms / 1000
        self._no_speech_s = no_speech_s
        self._max_utterance_s = max_utterance_s
        self._frame_s = frame_samples / SAMPLE_RATE
        self._capture: _Capture | None = None
        self.detections = 0

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Capture the running loop and start the listening thread."""
        if self._thread is not None:
            return
        self._loop = loop or asyncio.get_running_loop()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="zeno-wake-word", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the thread to finish and wait briefly for it. Safe to call twice."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
        self._thread = None

    def _run(self) -> None:
        try:
            detector = self._detector_factory()
            stream = self._stream_factory()
        except Exception:
            log.exception("Wake word listener could not start; voice wake is off")
            return
        try:
            while not self._stop.is_set():
                try:
                    frame = stream.read(self._frame_samples)
                except Exception:
                    log.exception("Microphone read failed; stopping wake word listener")
                    break
                if not frame:  # the stream ended
                    break
                if self._capture is not None:
                    self._capture_frame(self._capture, frame)
                    continue
                hit = self._scan(detector, frame)
                if hit is not None:
                    self._deliver(*hit)
                    if self._capture_sink is not None:
                        self._begin_capture(detector)
        finally:
            if self._capture is not None:  # stopped mid-command: close the utterance
                self._hand_off(self._capture, b"", "stopped")
            try:
                stream.close()
            except Exception:
                log.debug("Closing the microphone stream failed", exc_info=True)

    def _begin_capture(self, detector: Detector) -> None:
        self._capture = _Capture(uuid.uuid4().hex)
        reset = getattr(detector, "reset", None)
        if callable(reset):  # so the tail of "Hey Zeno" can't fire again afterwards
            try:
                reset()
            except Exception:
                log.debug("Resetting the wake word model failed", exc_info=True)

    def _capture_frame(self, state: _Capture, frame: bytes) -> None:
        """CAPTURING: hand the frame on and decide whether the command is over."""
        state.elapsed += self._frame_s
        if self._is_speech(frame):
            state.heard_speech, state.silence = True, 0.0
        else:
            state.silence += self._frame_s
        end: EndReason | None = None
        # Compare with a little tolerance: the elapsed time is a sum of float frames.
        if state.heard_speech and state.silence >= self._silence_s - 1e-6:
            end = "silence"
        elif not state.heard_speech and state.elapsed >= self._no_speech_s - 1e-6:
            end = "no_speech"
        elif state.elapsed >= self._max_utterance_s - 1e-6:
            end = "max_length"
        self._hand_off(state, frame, end)

    def _hand_off(self, state: _Capture, frame: bytes, end: EndReason | None) -> None:
        chunk = AudioChunk(state.utterance_id, state.seq, frame, end is not None, end)
        state.seq += 1
        if end is not None:
            self._capture = None
        loop, sink = self._loop, self._capture_sink
        if loop is None or sink is None:
            return
        try:
            # asyncio queues are not thread-safe: the put must happen on the loop thread.
            loop.call_soon_threadsafe(sink, chunk)
        except RuntimeError:
            log.debug("Event loop gone; dropping captured audio")

    def _is_speech(self, frame: bytes) -> bool:
        """Any 20 ms sub-frame with speech makes the frame speech."""
        if self._vad is None:
            return True
        step = SAMPLE_RATE * VAD_FRAME_MS // 1000 * 2  # bytes per sub-frame
        try:
            return any(
                self._vad.is_speech(frame[i : i + step], SAMPLE_RATE)
                for i in range(0, len(frame) - step + 1, step)
            )
        except Exception:
            log.debug("Voice activity check failed; treating the frame as speech", exc_info=True)
            return True

    def _scan(self, detector: Detector, frame: bytes) -> tuple[str, float] | None:
        """The loudest model over the threshold, unless we just fired (refractory)."""
        try:
            scores = detector.predict(frame)
        except Exception:
            log.exception("Wake word model failed on a frame")
            return None
        if not scores:
            return None
        model, score = max(scores.items(), key=lambda item: item[1])
        if score < self._threshold:
            return None
        now = self._clock()
        if now - self._last_fire < self._refractory:
            return None
        self._last_fire = now
        return model, score

    def _deliver(self, model: str, score: float) -> None:
        """Hand the detection to the loop. The only thread->loop bridge here."""
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._publish, model, score)
        except RuntimeError:
            # The loop is closed (shutdown raced us); nothing more to do.
            log.debug("Event loop gone; dropping wake detection")

    def _publish(self, model: str, score: float) -> None:
        """Runs on the loop thread: put the event on the bus."""
        self.detections += 1
        self._bus.publish(
            DeviceEvent(
                device=DEVICE,
                kind="wake",
                data={"model": model, "confidence": round(score, 3)},
                received_at=time.time(),
            )
        )


def build_listener(
    settings: object, bus: EventBus, *, capture_sink: CaptureSink | None = None
) -> WakeWordListener:
    """Wire a listener from settings with the real (lazy) sounddevice + openwakeword
    factories. The imports only run when the thread starts, so this is safe to call
    anywhere; the daemon only starts it on Windows. With ``capture_sink`` the command
    after "Hey Zeno" is captured for the voice worker, ended by webrtcvad."""
    threshold = float(getattr(settings, "wakeword_confidence", 0.6))
    model_path = getattr(settings, "wakeword_model_path", None)
    detector = (
        default_detector_factory(str(model_path)) if model_path else _builtin_detector_factory()
    )
    vad = None
    if capture_sink is not None:
        vad = webrtc_vad(int(getattr(settings, "vad_aggressiveness", 2)))
    return WakeWordListener(
        bus,
        detector_factory=detector,
        stream_factory=default_stream_factory(),
        threshold=threshold,
        capture_sink=capture_sink,
        vad=vad,
        silence_ms=int(getattr(settings, "vad_silence_ms", 800)),
        no_speech_s=float(getattr(settings, "voice_no_speech_s", 5.0)),
        max_utterance_s=float(getattr(settings, "voice_max_utterance_s", 15.0)),
    )


def webrtc_vad(aggressiveness: int) -> Vad | None:
    """webrtcvad (from webrtcvad-wheels). None if it is missing: captures then end at
    the length cap instead of on silence."""
    try:
        import webrtcvad
    except ImportError:
        log.warning("webrtcvad is not installed; voice commands will end at the length cap")
        return None

    class _WebRtcVad:
        def __init__(self) -> None:
            self._vad = webrtcvad.Vad(aggressiveness)

        def is_speech(self, frame: bytes, sample_rate: int) -> bool:
            return bool(self._vad.is_speech(frame, sample_rate))

    return _WebRtcVad()


def _ensure_openwakeword_models() -> None:
    """Fetch openwakeword's model files once (idempotent, skips what exists).

    openwakeword ships no model files in its wheel; it downloads them on first use.
    tflite-runtime is a Linux-only dependency, so on Windows Zeno runs openwakeword
    under onnxruntime (a hard openwakeword dependency, always installed) and needs
    the ``.onnx`` feature and wake models present. ``download_models`` pulls both the
    tflite and onnx forms, so this covers the onnx inference framework below."""
    from openwakeword.utils import download_models

    download_models()


def _builtin_detector_factory() -> DetectorFactory:
    """openwakeword with its bundled models when no path is set."""

    def open_detector() -> Detector:
        import numpy as np
        from openwakeword.model import Model

        _ensure_openwakeword_models()
        model = Model(inference_framework="onnx")

        class _OpenWakeWord:
            def predict(self, frame: bytes) -> Mapping[str, float]:
                samples = np.frombuffer(frame, dtype=np.int16)
                return {name: float(score) for name, score in model.predict(samples).items()}

            def reset(self) -> None:
                model.reset()

        return _OpenWakeWord()

    return open_detector


def default_stream_factory(frame_samples: int = FRAME_SAMPLES) -> StreamFactory:
    """A sounddevice microphone stream. Imported lazily; Windows/optional."""

    def open_stream() -> AudioStream:
        import sounddevice  # optional, loaded only when voice wake is on

        stream = sounddevice.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=frame_samples,
        )
        stream.start()

        class _SoundDeviceStream:
            def read(self, frames: int) -> bytes:
                data, _overflowed = stream.read(frames)
                return bytes(data)

            def close(self) -> None:
                stream.stop()
                stream.close()

        return _SoundDeviceStream()

    return open_stream


def default_detector_factory(model_path: str) -> DetectorFactory:
    """An openwakeword model. Imported lazily; Windows/optional."""

    def open_detector() -> Detector:
        import numpy as np
        from openwakeword.model import Model

        _ensure_openwakeword_models()
        model = Model(wakeword_models=[model_path], inference_framework="onnx")

        class _OpenWakeWord:
            def predict(self, frame: bytes) -> Mapping[str, float]:
                samples = np.frombuffer(frame, dtype=np.int16)
                return {name: float(score) for name, score in model.predict(samples).items()}

            def reset(self) -> None:
                model.reset()

        return _OpenWakeWord()

    return open_detector
