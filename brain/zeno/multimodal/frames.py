"""FrameStore: images in memory only, behind a TTL and byte caps.

The bus never carries image bytes: ``put`` keeps them here and publishes a small
VisionFrameReceived with the frame's id. Nothing is ever written to disk.
"""

import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from zeno.senses.events import EventBus
from zeno.senses.protocol import VisionFrameReceived

Mime = Literal["image/jpeg", "image/png"]


class FrameRejectedError(ValueError):
    """The image was refused at the door (format or size)."""


class FrameNotFoundError(LookupError):
    """No such frame, or it expired."""


@dataclass(frozen=True, slots=True)
class Frame:
    id: str
    source: str
    mime: Mime
    data: bytes
    stored_at: float
    """On the store's (monotonic) clock, for the TTL."""


def sniff_mime(data: bytes) -> Mime | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


class FrameStore:
    def __init__(
        self,
        bus: EventBus | None,
        *,
        ttl: float = 60.0,
        max_total_bytes: int = 32 * 1024 * 1024,
        max_frame_bytes: int = 4 * 1024 * 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bus = bus
        self._ttl = ttl
        self._max_total = max_total_bytes
        self._max_frame = max_frame_bytes
        self._clock = clock
        self._frames: OrderedDict[str, Frame] = OrderedDict()
        self._latest: dict[str, str] = {}
        self.total_bytes = 0

    def put(self, data: bytes, *, source: str) -> Frame:
        """Keep an image and announce it on the bus. The format is sniffed, not trusted."""
        if len(data) > self._max_frame:
            raise FrameRejectedError(f"Images are limited to {self._max_frame} bytes.")
        mime = sniff_mime(data)
        if mime is None:
            raise FrameRejectedError("Only JPEG or PNG images can be analysed.")
        self._expire()
        frame = Frame(uuid.uuid4().hex, source, mime, data, self._clock())
        while self._frames and self.total_bytes + len(data) > self._max_total:
            self._evict(next(iter(self._frames)))
        self._frames[frame.id] = frame
        self._latest[source] = frame.id
        self.total_bytes += len(data)
        if self._bus is not None:
            event = VisionFrameReceived(
                frame_id=frame.id,
                source=source,
                mime=mime,
                size_bytes=len(data),
                received_at=time.time(),
            )
            self._bus.publish(event.to_event())
        return frame

    def get(self, frame_id: str | None) -> Frame:
        """A frame by id, or the newest one when ``frame_id`` is None."""
        self._expire()
        if frame_id is None:
            if not self._frames:
                raise FrameNotFoundError("There is no image to look at yet. Share one first.")
            return next(reversed(self._frames.values()))
        frame = self._frames.get(frame_id)
        if frame is None:
            raise FrameNotFoundError(f"No image with id {frame_id}; it may have expired.")
        return frame

    def latest(self, source: str) -> Frame | None:
        self._expire()
        frame_id = self._latest.get(source)
        return self._frames.get(frame_id) if frame_id is not None else None

    def _expire(self) -> None:
        cutoff = self._clock() - self._ttl
        while self._frames:
            oldest = next(iter(self._frames.values()))
            if oldest.stored_at > cutoff:
                return
            self._evict(oldest.id)

    def _evict(self, frame_id: str) -> None:
        frame = self._frames.pop(frame_id)
        self.total_bytes -= len(frame.data)
        if self._latest.get(frame.source) == frame_id:
            del self._latest[frame.source]
