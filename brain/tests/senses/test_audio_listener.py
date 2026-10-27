"""The wake-word listener: detection logic, the thread->loop bridge, clean shutdown.

No real microphone or model is ever touched; the stream and detector are fakes.
"""

import asyncio
import threading
from collections.abc import Mapping

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
