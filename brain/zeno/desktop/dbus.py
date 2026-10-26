"""D-Bus clients for desktop notifications and systemd unit status (dbus-fast).

One connection per bus, opened on first use and reopened if it drops. Without a
session bus (a headless server) or a system bus, calls raise ``DesktopUnavailable``
with a plain reason instead of crashing.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus

Scope = Literal["system", "user"]
URGENCY = {"low": 0, "normal": 1, "critical": 2}
_NOTIFY = ("org.freedesktop.Notifications", "/org/freedesktop/Notifications")
_SYSTEMD = ("org.freedesktop.systemd1", "/org/freedesktop/systemd1")


class DesktopUnavailable(Exception):
    """The bus or the service on it can't be reached."""


@dataclass(frozen=True, slots=True)
class UnitState:
    name: str
    description: str
    load: str
    active: str
    sub: str
    since: float | None
    """When it entered this state (Unix time), if systemd recorded it."""


class DbusDesktop:
    def __init__(
        self,
        *,
        session_address: str | None = None,
        system_address: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._addresses = {"user": session_address, "system": system_address}
        self._buses: dict[str, MessageBus] = {}
        self._timeout = timeout

    async def notify(self, title: str, body: str, urgency: str) -> int:
        """Show a notification; returns the id the notification server gave it."""
        reply = await self._call(
            "user",
            Message(
                destination=_NOTIFY[0],
                path=_NOTIFY[1],
                interface="org.freedesktop.Notifications",
                member="Notify",
                signature="susssasa{sv}i",
                body=[
                    "Zeno",
                    0,
                    "",
                    title,
                    body,
                    [],
                    {"urgency": Variant("y", URGENCY[urgency])},
                    -1,
                ],
            ),
            unreachable="no desktop session to show notifications on",
        )
        return int(reply.body[0])

    async def unit_state(self, name: str, scope: Scope) -> UnitState | None:
        """A systemd unit's state, or None when systemd has no such unit loaded."""
        reply = await self._call(
            scope,
            Message(
                destination=_SYSTEMD[0],
                path=_SYSTEMD[1],
                interface="org.freedesktop.systemd1.Manager",
                member="GetUnit",
                signature="s",
                body=[name],
            ),
            unreachable=f"can't reach the {scope} systemd",
            missing="org.freedesktop.systemd1.NoSuchUnit",
        )
        if reply is None:
            return None
        props = await self._call(
            scope,
            Message(
                destination=_SYSTEMD[0],
                path=str(reply.body[0]),
                interface="org.freedesktop.DBus.Properties",
                member="GetAll",
                signature="s",
                body=["org.freedesktop.systemd1.Unit"],
            ),
            unreachable=f"can't read {name} from systemd",
        )
        values: dict[str, Any] = {key: variant.value for key, variant in props.body[0].items()}
        stamp = int(values.get("StateChangeTimestamp", 0))
        return UnitState(
            str(values.get("Id", name)),
            str(values.get("Description", "")),
            str(values.get("LoadState", "")),
            str(values.get("ActiveState", "")),
            str(values.get("SubState", "")),
            stamp / 1_000_000 if stamp else None,
        )

    async def close(self) -> None:
        for bus in self._buses.values():
            bus.disconnect()
        self._buses.clear()

    async def _bus(self, scope: str) -> MessageBus:
        bus = self._buses.get(scope)
        if bus is not None and bus.connected:
            return bus
        kind = BusType.SESSION if scope == "user" else BusType.SYSTEM
        try:
            async with asyncio.timeout(self._timeout):
                bus = await MessageBus(bus_address=self._addresses[scope], bus_type=kind).connect()
        except Exception as error:  # dbus-fast raises several types for a missing bus
            raise DesktopUnavailable(f"no {scope} D-Bus ({error})") from error
        self._buses[scope] = bus
        return bus

    async def _call(
        self, scope: str, message: Message, *, unreachable: str, missing: str | None = None
    ) -> Any:
        try:
            bus = await self._bus(scope)
        except DesktopUnavailable as error:
            raise DesktopUnavailable(unreachable) from error
        try:
            async with asyncio.timeout(self._timeout):
                reply = await bus.call(message)
        except (TimeoutError, OSError, EOFError) as error:
            self._buses.pop(scope, None)
            raise DesktopUnavailable(unreachable) from error
        if reply is None:
            raise DesktopUnavailable(unreachable)
        if reply.message_type == MessageType.ERROR:
            if missing is not None and reply.error_name == missing:
                return None
            detail = reply.body[0] if reply.body else reply.error_name
            raise DesktopUnavailable(f"{unreachable}: {detail}")
        return reply
