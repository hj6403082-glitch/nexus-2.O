"""The standard built-in tools."""

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tests.memory.conftest import Clock
from tests.senses.test_manager import FakeSocket
from zeno.agent.tools import builtin_registry
from zeno.agent.tools.base import Risk, Tool
from zeno.agent.tools.calculator import CalcArgs, calculate
from zeno.agent.tools.clock import TimeArgs, get_time
from zeno.agent.tools.devices import (
    CommandArgs,
    NoArgs,
    SensorArgs,
    SensorCache,
    device_tools,
)
from zeno.agent.tools.memory import FactArgs, RecallArgs, memory_tools
from zeno.agent.tools.system import SystemArgs, get_system_info
from zeno.memory.episodic import EpisodicMemory
from zeno.memory.fake import HashEmbedder, InMemoryVectorStore
from zeno.memory.manager import MemoryManager
from zeno.memory.semantic import FactMemory
from zeno.senses.events import DeviceEvent, EventBus
from zeno.senses.manager import ConnectionManager
from zeno.senses.protocol import CommandResult


def by_name(tools: list[Tool]) -> dict[str, Tool]:
    return {t.name: t for t in tools}


# --- time ---------------------------------------------------------------------------


async def test_get_time_in_utc() -> None:
    text = await get_time.invoke(TimeArgs(timezone="UTC"))
    stamp = datetime.fromisoformat(text.split(" ")[0])
    assert abs(stamp - datetime.now(UTC)) < timedelta(seconds=5)
    assert "UTC" in text


async def test_get_time_defaults_to_local_time() -> None:
    text = await get_time.invoke(TimeArgs())
    stamp = datetime.fromisoformat(text.split(" ")[0])
    assert stamp.tzinfo is not None


async def test_get_time_rejects_unknown_zones() -> None:
    with pytest.raises(ValueError, match="time zone"):
        await get_time.invoke(TimeArgs(timezone="Mars/Olympus"))


@pytest.mark.parametrize("zone", ["../../etc/passwd", "/etc/localtime", "UTC; rm"])
def test_get_time_zone_names_are_validated(zone: str) -> None:
    with pytest.raises(ValueError):
        TimeArgs(timezone=zone)


# --- calculator ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 + 3", "5"),
        ("2 * (3 + 4)", "14"),
        ("-7 // 2", "-4"),
        ("10 / 4", "2.5"),
        ("2 ** 10", "1024"),
        ("7 % 3", "1"),
        ("1.5 + 1.5", "3.0"),
        ("+3", "3"),
    ],
)
async def test_calculate(expression: str, expected: str) -> None:
    assert await calculate.invoke(CalcArgs(expression=expression)) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",
        "open('x')",
        "a + 1",
        "[1, 2]",
        "(lambda: 1)()",
        "'a' * 3",
        "1 if 1 else 2",
        "2 ** 2 ** 2 ** 2 ** 2",  # far too large
        "9 ** 9 ** 9",  # would take minutes and gigabytes if computed first
        "10 ** 400",
        "1 / 0",
        "",
    ],
)
async def test_calculate_refuses_anything_but_arithmetic(expression: str) -> None:
    with pytest.raises(ValueError):
        await calculate.invoke(CalcArgs(expression=expression))


async def test_calculate_rejects_non_finite_results() -> None:
    with pytest.raises(ValueError):
        await calculate.invoke(CalcArgs(expression="1e308 * 10"))
    assert math.isfinite(float(await calculate.invoke(CalcArgs(expression="1e300 * 10"))))


# --- system -------------------------------------------------------------------------


async def test_system_info_reports_the_platform() -> None:
    text = await get_system_info.invoke(SystemArgs())
    assert "Python" in text
    assert "CPUs" in text


# --- memory -------------------------------------------------------------------------


@pytest.fixture
def memory() -> MemoryManager:
    store, embedder, clock = InMemoryVectorStore(), HashEmbedder(), Clock()
    return MemoryManager(
        facts=FactMemory(store, embedder, clock=clock),
        episodes=EpisodicMemory(store, embedder, clock=clock),
        min_similarity=0.2,
    )


async def test_remember_then_recall(memory: MemoryManager) -> None:
    tools = by_name(memory_tools(memory))
    assert await tools["remember_fact"].invoke(FactArgs(fact="Boss likes the green theme"))
    facts = await memory.facts.all()
    assert [f.text for f in facts] == ["Boss likes the green theme"]
    assert facts[0].source == "agent"
    recalled = await tools["recall_memory"].invoke(RecallArgs(query="green theme"))
    assert "Boss likes the green theme" in recalled


async def test_recall_with_nothing_relevant(memory: MemoryManager) -> None:
    text = await by_name(memory_tools(memory))["recall_memory"].invoke(RecallArgs(query="x"))
    assert "nothing" in text.lower()


def test_memory_tool_risks(memory: MemoryManager) -> None:
    tools = by_name(memory_tools(memory))
    assert tools["recall_memory"].risk is Risk.READ_ONLY
    assert tools["remember_fact"].risk is Risk.MUTATING


# --- devices ------------------------------------------------------------------------


CAPS = frozenset({"sensor.temperature", "relay.fan"})


async def test_list_devices() -> None:
    manager = ConnectionManager()
    tools = by_name(device_tools(manager, SensorCache(), command_timeout=1.0))
    assert "No devices" in await tools["list_devices"].invoke(NoArgs())
    await manager.connect("pi-lab", FakeSocket(), CAPS)
    text = await tools["list_devices"].invoke(NoArgs())
    assert "pi-lab" in text and "relay.fan" in text and "sensor.temperature" in text


async def test_sensor_cache_keeps_the_latest_reading_from_the_bus() -> None:
    bus = EventBus()
    cache = SensorCache()
    cache.attach(bus)
    await bus.start()
    for value in (20.5, 21.0):
        bus.publish(
            DeviceEvent(
                "pi-lab",
                "sensor",
                {"sensor": "sensor.temperature", "value": value, "unit": "C"},
                received_at=100.0,
            )
        )
    bus.publish(DeviceEvent("pi-lab", "telemetry", {"metrics": {"cpu": 1}}, received_at=1.0))
    await bus.drain()
    await bus.stop()
    tools = by_name(device_tools(ConnectionManager(), cache, command_timeout=1.0))
    text = await tools["read_sensor"].invoke(
        SensorArgs(device="pi-lab", sensor="sensor.temperature")
    )
    assert "21.0" in text and "C" in text
    missing = await tools["read_sensor"].invoke(SensorArgs(device="pi-lab", sensor="sensor.light"))
    assert "No reading" in missing


async def test_send_device_command_round_trip() -> None:
    manager = ConnectionManager()
    socket = FakeSocket()
    conn = await manager.connect("pi-lab", socket, CAPS)
    tools = by_name(device_tools(manager, SensorCache(), command_timeout=1.0))

    async def answer() -> None:
        await socket.on_send.wait()
        command: dict[str, Any] = socket.sent[-1]
        manager.resolve(
            conn, CommandResult(command_id=str(command["id"]), ok=True, detail="fan on")
        )

    import asyncio

    responder = asyncio.create_task(answer())
    text = await tools["send_device_command"].invoke(
        CommandArgs(device="pi-lab", action="relay.fan", args={"on": True})
    )
    await responder
    assert "fan on" in text
    assert socket.sent[-1]["action"] == "relay.fan"


async def test_device_command_errors_surface_as_exceptions() -> None:
    from zeno.senses.manager import CapabilityNotDeclared, DeviceNotConnected

    manager = ConnectionManager()
    tools = by_name(device_tools(manager, SensorCache(), command_timeout=1.0))
    with pytest.raises(DeviceNotConnected):
        await tools["send_device_command"].invoke(CommandArgs(device="pi-lab", action="relay.fan"))
    await manager.connect("pi-lab", FakeSocket(), CAPS)
    with pytest.raises(CapabilityNotDeclared):
        await tools["send_device_command"].invoke(CommandArgs(device="pi-lab", action="relay.door"))


async def test_device_command_tool_outlasts_the_device_timeout() -> None:
    tools = by_name(device_tools(ConnectionManager(), SensorCache(), command_timeout=3.0))
    assert tools["send_device_command"].timeout > 3.0


@pytest.mark.parametrize("device", ["PI", "../etc", "a", "x" * 60])
def test_device_ids_are_validated(device: str) -> None:
    with pytest.raises(ValueError):
        SensorArgs(device=device, sensor="sensor.temperature")


def test_device_tool_risks() -> None:
    tools = by_name(device_tools(ConnectionManager(), SensorCache(), command_timeout=1.0))
    assert tools["list_devices"].risk is Risk.READ_ONLY
    assert tools["read_sensor"].risk is Risk.READ_ONLY
    assert tools["send_device_command"].risk is Risk.MUTATING


# --- the standard set ---------------------------------------------------------------


def test_builtin_registry_without_optional_pillars() -> None:
    assert builtin_registry().names() == ["get_time", "calculate", "get_system_info"]


def test_builtin_registry_with_everything(memory: MemoryManager) -> None:
    registry = builtin_registry(
        memory=memory, devices=ConnectionManager(), sensors=SensorCache(), command_timeout=2.0
    )
    assert registry.names() == [
        "get_time",
        "calculate",
        "get_system_info",
        "recall_memory",
        "remember_fact",
        "list_devices",
        "read_sensor",
        "send_device_command",
    ]
    mutating = {t.name for t in registry if t.risk is Risk.MUTATING}
    assert mutating == {"remember_fact", "send_device_command"}
