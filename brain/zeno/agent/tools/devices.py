"""Edge devices: list them, read their latest sensor values, send them commands."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import Field, StringConstraints

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool
from zeno.senses.auth import DEVICE_ID
from zeno.senses.events import DeviceEvent, EventBus
from zeno.senses.manager import ConnectionManager
from zeno.senses.protocol import Capability, Key, Scalar

DeviceId = Annotated[str, StringConstraints(pattern=DEVICE_ID.pattern)]


class NoArgs(ToolArgs):
    pass


class SensorArgs(ToolArgs):
    device: DeviceId
    sensor: Capability = Field(
        description="A capability the device declared, e.g. sensor.temperature."
    )


class CommandArgs(ToolArgs):
    device: DeviceId
    action: Capability = Field(description="A capability the device declared, e.g. relay.fan.")
    args: dict[Key, Scalar] = Field(default_factory=dict, max_length=16)


@dataclass(frozen=True, slots=True)
class Reading:
    value: Any
    unit: str | None
    received_at: float


class SensorCache:
    """The latest value of every sensor, kept current from the senses event bus."""

    def __init__(self) -> None:
        self._latest: dict[tuple[str, str], Reading] = {}

    def attach(self, bus: EventBus) -> Callable[[], None]:
        return bus.subscribe(self.handle, kind="sensor")

    async def handle(self, event: DeviceEvent) -> None:
        if event.kind == "sensor":
            data = event.data
            self._latest[(event.device, str(data["sensor"]))] = Reading(
                data.get("value"), data.get("unit"), event.received_at
            )

    def latest(self, device: str, sensor: str) -> Reading | None:
        return self._latest.get((device, sensor))


def device_tools(
    manager: ConnectionManager, sensors: SensorCache, *, command_timeout: float
) -> list[Tool[Any]]:
    @tool(risk=Risk.READ_ONLY, timeout=2.0)
    async def list_devices(args: NoArgs) -> str:
        """List the connected edge devices and the capabilities each one declared."""
        lines = []
        for device in manager.devices():
            conn = manager.get(device)
            if conn is not None:
                lines.append(f"- {device}: {', '.join(sorted(conn.capabilities)) or 'none'}")
        return "\n".join(lines) if lines else "No devices are connected."

    @tool(risk=Risk.READ_ONLY, timeout=2.0)
    async def read_sensor(args: SensorArgs) -> str:
        """Read the latest value a device reported for one of its sensors."""
        reading = sensors.latest(args.device, args.sensor)
        if reading is None:
            return f"No reading from {args.device} {args.sensor} yet."
        unit = f" {reading.unit}" if reading.unit else ""
        when = datetime.fromtimestamp(reading.received_at, UTC).astimezone()
        return (
            f"{args.device} {args.sensor} = {reading.value}{unit} "
            f"(at {when.isoformat(timespec='seconds')})"
        )

    # Outlasts the device's own deadline so the device's timeout is the one reported.
    @tool(risk=Risk.MUTATING, timeout=command_timeout + 1.0)
    async def send_device_command(args: CommandArgs) -> str:
        """Send a command to a device, for one of the capabilities it declared."""
        result = await manager.send_command(
            args.device, args.action, args.args, timeout=command_timeout
        )
        status = "done" if result.ok else "failed"
        detail = f": {result.detail}" if result.detail else ""
        data = f" {dict(result.data)}" if result.data else ""
        return f"{args.device} {args.action} {status}{detail}{data}"

    return [list_devices, read_sensor, send_device_command]
