import asyncio
import io
from collections.abc import AsyncIterator, Callable

import pytest
from PIL import Image

from zeno.senses.events import DeviceEvent, EventBus, EventKind


def png(width: int = 32, height: int = 24, color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg(width: int = 32, height: int = 24) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "blue").save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
async def bus() -> AsyncIterator[EventBus]:
    bus = EventBus(maxsize=100)
    await bus.start()
    yield bus
    await bus.stop()


class Recorder:
    """Collects bus events of one kind."""

    def __init__(self, bus: EventBus, kind: EventKind) -> None:
        self.events: list[DeviceEvent] = []
        self.arrived = asyncio.Event()

        async def record(event: DeviceEvent) -> None:
            self.events.append(event)
            self.arrived.set()

        bus.subscribe(record, kind=kind)


@pytest.fixture
def record(bus: EventBus) -> Callable[[EventKind], Recorder]:
    return lambda kind: Recorder(bus, kind)


async def eventually(condition: Callable[[], bool], limit: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + limit
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.005)
