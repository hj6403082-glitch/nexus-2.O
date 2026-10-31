"""Ports for the multimodal engines. Every method here is synchronous on purpose: it
only ever runs on a worker's own thread, never on the event loop."""

from dataclasses import dataclass
from typing import Protocol


class MultimodalError(Exception):
    """A vision or voice engine could not do its job."""


class EngineUnavailableError(MultimodalError):
    """The engine's package or model file is missing; the message says how to fix it."""


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str = "en"
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class Audio:
    """Mono 16-bit PCM."""

    pcm: bytes
    sample_rate: int


class VisionEngine(Protocol):
    def describe(self, image: bytes, mime: str, question: str, *, max_tokens: int) -> str: ...

    def close(self) -> None: ...


class SttEngine(Protocol):
    def transcribe(self, pcm: bytes, sample_rate: int) -> Transcript: ...

    def close(self) -> None: ...


class TtsEngine(Protocol):
    def synthesize(self, text: str) -> Audio: ...

    def close(self) -> None: ...


class AudioSink(Protocol):
    def play(self, audio: Audio) -> None:
        """Play until done or until ``stop`` is called. Blocks; runs on its own thread."""
        ...

    def stop(self) -> None:
        """Cut the current playback short. Called from the loop thread; must be thread-safe."""
        ...
