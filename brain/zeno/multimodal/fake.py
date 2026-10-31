"""Fakes for the multimodal engines, used by every default test (no model, no device)."""

import threading
import time

from zeno.multimodal.base import Audio, Transcript


class FakeVisionEngine:
    """Always sees "a test image"; records each call and the thread it ran on."""

    def __init__(
        self,
        answer: str = "I see a test image",
        *,
        delay: float = 0.0,
        fail: Exception | None = None,
    ) -> None:
        self.answer = answer
        self.delay = delay
        self.fail = fail
        self.calls: list[tuple[bytes, str, str, int]] = []
        self.started = 0
        self.thread: int | None = None
        self.closed = False

    def describe(self, image: bytes, mime: str, question: str, *, max_tokens: int) -> str:
        self.started += 1
        self.thread = threading.get_ident()
        if self.delay:
            time.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        self.calls.append((image, mime, question, max_tokens))
        return self.answer

    def close(self) -> None:
        self.closed = True


class FakeSttEngine:
    """Hears "Test command" in any audio."""

    def __init__(self, text: str = "Test command", *, fail: Exception | None = None) -> None:
        self.text = text
        self.fail = fail
        self.calls: list[tuple[bytes, int]] = []
        self.thread: int | None = None
        self.closed = False

    def transcribe(self, pcm: bytes, sample_rate: int) -> Transcript:
        self.thread = threading.get_ident()
        if self.fail is not None:
            raise self.fail
        self.calls.append((pcm, sample_rate))
        return Transcript(self.text, "en", 0.9)

    def close(self) -> None:
        self.closed = True


class FakeTtsEngine:
    """Turns any text into a short silent clip."""

    def __init__(self, *, fail: Exception | None = None) -> None:
        self.fail = fail
        self.calls: list[str] = []
        self.closed = False

    def synthesize(self, text: str) -> Audio:
        if self.fail is not None:
            raise self.fail
        self.calls.append(text)
        return Audio(b"\x00\x00" * 160, 16000)

    def close(self) -> None:
        self.closed = True


class FakeAudioSink:
    """Records what it played. With ``block`` set, a clip "plays" until ``stop``."""

    def __init__(self) -> None:
        self.played: list[Audio] = []
        self.block = False
        self.playing = False
        self.stopped = False
        self.thread: int | None = None
        self._stop = threading.Event()

    def play(self, audio: Audio) -> None:
        self.thread = threading.get_ident()
        self._stop.clear()
        self.playing = True
        try:
            while self.block and not self._stop.wait(0.005):
                pass
            self.played.append(audio)
        finally:
            self.playing = False

    def stop(self) -> None:
        self.stopped = True
        self._stop.set()
