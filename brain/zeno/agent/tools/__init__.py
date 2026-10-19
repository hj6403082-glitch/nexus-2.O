"""Built-in tools. Each is a fixed implementation with validated arguments."""

from typing import Any

from zeno.agent.registry import ToolRegistry
from zeno.agent.tools.base import Tool
from zeno.agent.tools.calculator import calculate
from zeno.agent.tools.clock import get_time
from zeno.agent.tools.devices import SensorCache, device_tools
from zeno.agent.tools.memory import memory_tools
from zeno.agent.tools.system import get_system_info
from zeno.memory.manager import MemoryManager
from zeno.senses.manager import ConnectionManager


def builtin_registry(
    *,
    memory: MemoryManager | None = None,
    devices: ConnectionManager | None = None,
    sensors: SensorCache | None = None,
    command_timeout: float = 5.0,
) -> ToolRegistry:
    """The standard tool set. Memory and device tools join when those pillars are wired."""
    tools: list[Tool[Any]] = [get_time, calculate, get_system_info]
    if memory is not None:
        tools += memory_tools(memory)
    if devices is not None:
        tools += device_tools(devices, sensors or SensorCache(), command_timeout=command_timeout)
    return ToolRegistry(tools)
