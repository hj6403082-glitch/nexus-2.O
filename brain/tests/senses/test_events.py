import asyncio
from collections.abc import AsyncIterator

import pytest

from zeno.senses.events import DeviceEvent, EventBus


def event(n: int, kind: str = "sensor") -> DeviceEvent:
    return DeviceEvent(device="pi-test", kind=kind, data={"n": n}, received_at=float(n))  # type: ignore[arg-type]


@pytest.fixture
async def bus() -> AsyncIterator[EventBus]:
    bus = EventBus(maxsize=100)
    await bus.start()
    yield bus
    await bus.stop()


async def test_delivers_events_in_order_to_every_subscriber(bus: EventBus) -> None:
    first: list[int] = []
    second: list[int] = []

    async def one(e: DeviceEvent) -> None:
        first.append(e.data["n"])

    async def two(e: DeviceEvent) -> None:
        second.append(e.data["n"])

    bus.subscribe(one)
    bus.subscribe(two)
    for n in range(5):
        bus.publish(event(n))
    await bus.drain()
    assert first == second == [0, 1, 2, 3, 4]


async def test_kind_filter(bus: EventBus) -> None:
    seen: list[str] = []

    async def handler(e: DeviceEvent) -> None:
        seen.append(e.kind)

    bus.subscribe(handler, kind="telemetry")
    bus.publish(event(1, "sensor"))
    bus.publish(event(2, "telemetry"))
    await bus.drain()
    assert seen == ["telemetry"]


async def test_publish_never_waits_for_slow_handlers(bus: EventBus) -> None:
    release = asyncio.Event()

    async def slow(e: DeviceEvent) -> None:
        await release.wait()

    bus.subscribe(slow)
    loop = asyncio.get_running_loop()
    start = loop.time()
    for n in range(50):
        bus.publish(event(n))
    assert loop.time() - start < 0.05
    release.set()
    await bus.drain()


async def test_a_full_queue_drops_the_oldest_events() -> None:
    bus = EventBus(maxsize=3)
    seen: list[int] = []

    async def handler(e: DeviceEvent) -> None:
        seen.append(e.data["n"])

    bus.subscribe(handler)
    for n in range(5):  # not started yet, so nothing is consumed
        bus.publish(event(n))
    assert bus.dropped == 2
    await bus.start()
    await bus.drain()
    await bus.stop()
    assert seen == [2, 3, 4]


async def test_a_failing_handler_does_not_break_others(bus: EventBus) -> None:
    seen: list[int] = []

    async def broken(e: DeviceEvent) -> None:
        raise RuntimeError("boom")

    async def fine(e: DeviceEvent) -> None:
        seen.append(e.data["n"])

    bus.subscribe(broken)
    bus.subscribe(fine)
    bus.publish(event(1))
    bus.publish(event(2))
    await bus.drain()
    assert seen == [1, 2]
    assert bus.errors == 2


async def test_unsubscribe(bus: EventBus) -> None:
    seen: list[int] = []

    async def handler(e: DeviceEvent) -> None:
        seen.append(e.data["n"])

    unsubscribe = bus.subscribe(handler)
    bus.publish(event(1))
    await bus.drain()
    unsubscribe()
    bus.publish(event(2))
    await bus.drain()
    assert seen == [1]


async def test_stop_delivers_what_is_queued_then_ignores_new_events() -> None:
    bus = EventBus()
    seen: list[int] = []

    async def handler(e: DeviceEvent) -> None:
        await asyncio.sleep(0.01)
        seen.append(e.data["n"])

    bus.subscribe(handler)
    await bus.start()
    for n in range(3):
        bus.publish(event(n))
    await bus.stop()
    assert seen == [0, 1, 2]
    bus.publish(event(9))
    await asyncio.sleep(0.02)
    assert seen == [0, 1, 2]
