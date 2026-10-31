"""FrameStore: images live in memory only, behind a TTL and byte caps; the bus gets a
small VisionFrameReceived event, never the bytes."""

from collections.abc import Callable

import pytest

from tests.multimodal.conftest import Recorder, eventually, jpeg, png
from zeno.multimodal.frames import FrameNotFoundError, FrameRejectedError, FrameStore
from zeno.senses.events import EventBus, EventKind
from zeno.senses.protocol import VisionFrameReceived


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


async def test_put_stores_and_publishes_a_small_event(
    bus: EventBus, record: Callable[[EventKind], Recorder]
) -> None:
    seen = record("vision_frame")
    store = FrameStore(bus)
    data = png()
    frame = store.put(data, source="upload")
    assert frame.mime == "image/png"
    assert store.get(frame.id).data == data
    await eventually(lambda: bool(seen.events))
    event = VisionFrameReceived.from_event(seen.events[0])
    assert event.frame_id == frame.id
    assert event.size_bytes == len(data)
    assert event.source == "upload"


def test_mime_is_sniffed_not_trusted() -> None:
    store = FrameStore(None)
    assert store.put(jpeg(), source="webcam").mime == "image/jpeg"
    with pytest.raises(FrameRejectedError, match="JPEG or PNG"):
        store.put(b"GIF89a" + b"\x00" * 20, source="upload")


def test_oversized_frames_are_refused() -> None:
    store = FrameStore(None, max_frame_bytes=100)
    with pytest.raises(FrameRejectedError, match="100 bytes"):
        store.put(png(200, 200), source="upload")


def test_latest_frame_when_no_id_is_given() -> None:
    store = FrameStore(None)
    store.put(png(), source="upload")
    second = store.put(jpeg(), source="webcam")
    assert store.get(None).id == second.id
    assert store.latest("upload") is not None


def test_frames_expire_after_the_ttl() -> None:
    clock = Clock()
    store = FrameStore(None, ttl=60.0, clock=clock)
    frame = store.put(png(), source="upload")
    clock.now += 61
    with pytest.raises(FrameNotFoundError):
        store.get(frame.id)
    with pytest.raises(FrameNotFoundError):
        store.get(None)


def test_total_bytes_are_capped_oldest_evicted_first() -> None:
    one = png()
    store = FrameStore(None, max_total_bytes=len(one) * 2 + 10)
    first = store.put(one, source="a")
    second = store.put(png(color="green"), source="b")
    third = store.put(png(color="blue"), source="c")
    with pytest.raises(FrameNotFoundError):
        store.get(first.id)
    assert store.get(second.id) and store.get(third.id)
    assert store.total_bytes <= len(one) * 2 + 10


def test_unknown_frame() -> None:
    with pytest.raises(FrameNotFoundError):
        FrameStore(None).get("nope")
