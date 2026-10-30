"""In-process event bus that decouples device sockets from whatever consumes sensor data.

``publish`` never awaits: socket loops hand events off and go straight back to
reading. One dispatcher task delivers events to subscribers in order. When the
queue is full the oldest event is dropped, because fresh sensor data matters more
than a complete backlog.
"""

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

log = logging.getLogger(__name__)

EventKind = Literal["connected", "disconnected", "sensor", "telemetry", "wake"]
Handler = Callable[["DeviceEvent"], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class DeviceEvent:
    device: str
    kind: EventKind
    data: Mapping[str, Any]
    received_at: float


class EventBus:
    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: deque[DeviceEvent] = deque()
        self._maxsize = maxsize
        self._subscribers: list[tuple[EventKind | None, Handler]] = []
        self._wakeup = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self.dropped = 0
        self.errors = 0

    def subscribe(self, handler: Handler, *, kind: EventKind | None = None) -> Callable[[], None]:
        entry = (kind, handler)
        self._subscribers.append(entry)

        def unsubscribe() -> None:
            if entry in self._subscribers:
                self._subscribers.remove(entry)

        return unsubscribe

    def publish(self, event: DeviceEvent) -> None:
        if self._stopping:
            self.dropped += 1
            return
        if len(self._queue) >= self._maxsize:
            self._queue.popleft()
            self.dropped += 1
        self._queue.append(event)
        self._idle.clear()
        self._wakeup.set()

    async def start(self) -> None:
        if self._task is None:
            self._stopping = False
            self._task = asyncio.create_task(self._run(), name="zeno-event-bus")

    async def drain(self) -> None:
        """Wait until every queued event has been handled."""
        await self._idle.wait()

    async def stop(self) -> None:
        """Deliver what is already queued, then stop. Later events are ignored."""
        self._stopping = True
        self._wakeup.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            while self._queue:
                await self._deliver(self._queue.popleft())
            self._idle.set()
            if self._stopping:
                return
            self._wakeup.clear()
            await self._wakeup.wait()

    async def _deliver(self, event: DeviceEvent) -> None:
        for kind, handler in list(self._subscribers):
            if kind is not None and kind != event.kind:
                continue
            try:
                await handler(event)
            except Exception:
                self.errors += 1
                log.exception("Event handler failed for %s event from %s", event.kind, event.device)
