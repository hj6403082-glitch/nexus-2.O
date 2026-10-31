"""The wake-word listener: detection logic, the thread->loop bridge, clean shutdown.

No real microphone or model is ever touched; the stream and detector are fakes.
"""

import asyncio
import threading
from collections.abc import Mapping

from zeno.multimodal.queues import AudioChunk
from zeno.senses.audio_listener import WakeWordListener
from zeno.senses.events import EventBus


class FakeStream:
    """Yields queued frames, then blocks until closed (like a live mic going quiet)."""

    def __init__(self, frames: list[bytes]) -> None:
        self._frames = list(frames)
        self._gate = threading.Event()
        self.closed = False

    def read(self, frames: int) -> bytes:
        if self._frames:
            return self._frames.pop(0)
        self._gate.wait(1.0)  # no more canned audio: wait to be closed
        return b""

    def close(self) -> None:
        self.closed = True
        self._gate.set()


class FakeDetector:
    """Scores a frame by a lookup table keyed on the frame's bytes."""

    def __init__(self, scores: dict[bytes, Mapping[str, float]]) -> None:
        self._scores = scores

    def predict(self, frame: bytes) -> Mapping[str, float]:
        return self._scores.get(frame, {"hey_zeno": 0.0})


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def listener(
    bus: EventBus, stream: FakeStream, detector: FakeDetector, **kw: object
) -> WakeWordListener:
    return WakeWordListener(
        bus,
        detector_factory=lambda: detector,
        stream_factory=lambda: stream,
        **kw,  # type: ignore[arg-type]
    )


def test_a_quiet_frame_fires_nothing() -> None:
    wl = listener(EventBus(), FakeStream([]), FakeDetector({}))
    assert wl._scan(FakeDetector({b"x": {"hey_zeno": 0.1}}), b"x") is None


def test_a_loud_frame_detects_the_model() -> None:
    wl = listener(EventBus(), FakeStream([]), FakeDetector({}), threshold=0.6)
    hit = wl._scan(FakeDetector({b"x": {"hey_zeno": 0.9, "other": 0.2}}), b"x")
    assert hit == ("hey_zeno", 0.9)


def test_the_refractory_period_swallows_repeats() -> None:
    clock = Clock()
    wl = listener(
        EventBus(), FakeStream([]), FakeDetector({}), threshold=0.6, refractory=2.0, clock=clock
    )
    det = FakeDetector({b"x": {"hey_zeno": 0.9}})
    assert wl._scan(det, b"x") == ("hey_zeno", 0.9)
    assert wl._scan(det, b"x") is None  # too soon
    clock.now += 2.0
    assert wl._scan(det, b"x") == ("hey_zeno", 0.9)  # past the refractory window


async def test_a_detection_reaches_the_bus_from_the_thread() -> None:
    bus = EventBus()
    await bus.start()
    heard: list[tuple[str, float]] = []

    async def on_wake(event: object) -> None:
        heard.append((event.data["model"], event.data["confidence"]))  # type: ignore[attr-defined]

    bus.subscribe(on_wake, kind="wake")
    stream = FakeStream([b"loud"])
    detector = FakeDetector({b"loud": {"hey_zeno": 0.95}})
    wl = listener(bus, stream, detector, threshold=0.6)

    wl.start()
    # The event crosses the thread via call_soon_threadsafe; give the loop a moment.
    for _ in range(100):
        await asyncio.sleep(0.01)
        if heard:
            break
    wl.stop()
    await bus.drain()
    await bus.stop()

    assert heard == [("hey_zeno", 0.95)]
    assert wl.detections == 1
    assert stream.closed


async def test_stop_joins_the_thread_even_while_it_waits_on_audio() -> None:
    bus = EventBus()
    await bus.start()
    stream = FakeStream([])  # nothing to read: the thread parks in stream.read
    wl = listener(bus, stream, FakeDetector({}))
    wl.start()
    await asyncio.sleep(0.02)
    wl.stop(timeout=1.0)
    assert wl._thread is None
    assert stream.closed
    await bus.stop()


def test_a_broken_microphone_does_not_raise() -> None:
    class Boom:
        def read(self, frames: int) -> bytes:
            raise OSError("mic unplugged")

        def close(self) -> None:
            pass

    bus = EventBus()
    wl = WakeWordListener(
        bus, detector_factory=lambda: FakeDetector({}), stream_factory=lambda: Boom()
    )
    wl._loop = asyncio.new_event_loop()
    try:
        wl._run()  # must swallow the error and return, not propagate
    finally:
        wl._loop.close()


def test_a_failed_start_is_swallowed() -> None:
    bus = EventBus()

    def boom() -> object:
        raise RuntimeError("no audio device")

    wl = WakeWordListener(bus, detector_factory=boom, stream_factory=boom)  # type: ignore[arg-type]
    wl._loop = asyncio.new_event_loop()
    try:
        wl._run()  # a missing mic must not crash the daemon
    finally:
        wl._loop.close()


# --- Wake-word handoff: after "Hey Zeno", microphone frames go to the voice worker ---

FRAME_BYTES = 2560  # 80 ms of 16 kHz int16
WAKE = b"W" * FRAME_BYTES
SPEECH = b"S" * FRAME_BYTES
SILENCE = b"\x00" * FRAME_BYTES


class FakeVad:
    """Speech is any sub-frame that is not all zeros."""

    def __init__(self) -> None:
        self.sizes: set[int] = set()

    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        self.sizes.add(len(frame))
        return frame[0] != 0


class ResettableDetector(FakeDetector):
    def __init__(self, scores: dict[bytes, Mapping[str, float]]) -> None:
        super().__init__(scores)
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1


async def capture(frames: list[bytes], **kw: object) -> tuple[list[AudioChunk], WakeWordListener]:
    """Run the listener over ``frames`` and collect what reached the capture sink."""
    bus = EventBus()
    await bus.start()
    chunks: list[AudioChunk] = []
    threads: set[int] = set()

    def sink(chunk: AudioChunk) -> None:
        threads.add(threading.get_ident())
        chunks.append(chunk)

    stream = FakeStream(frames)
    detector = ResettableDetector({WAKE: {"hey_zeno": 0.95}})
    wl = listener(
        bus, stream, detector, threshold=0.6, refractory=0.0, capture_sink=sink, vad=FakeVad(), **kw
    )
    wl.start()
    for _ in range(200):
        await asyncio.sleep(0.01)
        if stream.closed or (chunks and chunks[-1].final and not stream._frames):
            break
    wl.stop()
    await asyncio.sleep(0.02)  # let the last call_soon_threadsafe land
    await bus.drain()
    await bus.stop()
    assert threads <= {threading.get_ident()}  # the sink only ever runs on the loop thread
    wl.test_detector = detector  # type: ignore[attr-defined]
    return chunks, wl


async def test_after_the_wake_word_frames_go_to_the_sink_until_silence() -> None:
    chunks, wl = await capture([WAKE, SPEECH, SPEECH, *[SILENCE] * 10])
    assert [c.seq for c in chunks] == list(range(12))
    assert len({c.utterance_id for c in chunks}) == 1
    assert [c.final for c in chunks] == [False] * 11 + [True]
    assert chunks[-1].end_reason == "silence"
    assert chunks[0].pcm == SPEECH
    assert wl.detections == 1
    assert wl.test_detector.resets == 1  # type: ignore[attr-defined]


async def test_vad_sees_20_ms_sub_frames() -> None:
    vad = FakeVad()
    bus = EventBus()
    wl = listener(bus, FakeStream([]), FakeDetector({}), capture_sink=lambda c: None, vad=vad)
    assert wl._is_speech(SPEECH)
    assert vad.sizes == {640}


async def test_no_speech_after_the_wake_word_gives_up() -> None:
    chunks, _ = await capture([WAKE, *[SILENCE] * 8], no_speech_s=0.4)
    assert len(chunks) == 5
    assert chunks[-1].final and chunks[-1].end_reason == "no_speech"


async def test_an_endless_utterance_is_cut_at_the_cap() -> None:
    chunks, _ = await capture([WAKE, *[SPEECH] * 8], max_utterance_s=0.4)
    assert len(chunks) == 5
    assert chunks[-1].final and chunks[-1].end_reason == "max_length"


async def test_the_wake_model_is_not_scored_while_capturing() -> None:
    chunks, wl = await capture([WAKE, SPEECH, WAKE, SPEECH, *[SILENCE] * 10])
    assert wl.detections == 1
    assert chunks[1].pcm == WAKE  # captured like any other audio


async def test_listening_resumes_after_an_utterance() -> None:
    chunks, wl = await capture([WAKE, SPEECH, *[SILENCE] * 10, WAKE, SPEECH, *[SILENCE] * 10])
    assert wl.detections == 2
    ids = [c.utterance_id for c in chunks]
    assert len(set(ids)) == 2
    assert sum(c.final for c in chunks) == 2


async def test_the_stream_ending_mid_utterance_closes_it() -> None:
    chunks, _ = await capture([WAKE, SPEECH, SPEECH])
    assert chunks[-1].final and chunks[-1].end_reason == "stopped"


async def test_without_a_sink_nothing_is_captured() -> None:
    bus = EventBus()
    await bus.start()
    stream = FakeStream([WAKE, SPEECH, WAKE])
    wl = listener(bus, stream, FakeDetector({WAKE: {"hey_zeno": 0.95}}), refractory=0.0)
    wl.start()
    for _ in range(200):
        await asyncio.sleep(0.01)
        if wl.detections == 2:
            break
    wl.stop()
    await bus.stop()
    assert wl.detections == 2  # today's behaviour: every wake frame fires
