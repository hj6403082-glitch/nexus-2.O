"""Tracks live device connections and the commands waiting on them."""

import asyncio
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Protocol

from zeno.senses.protocol import CloseCode, Command, CommandResult, _Frame, encode


class DeviceSocket(Protocol):
    async def send_text(self, data: str) -> None: ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


class SensesError(Exception):
    pass


class DeviceNotConnected(SensesError):
    pass


class CapabilityNotDeclared(SensesError):
    pass


class CommandTimeout(SensesError):
    pass


class DeviceDisconnected(SensesError):
    pass


@dataclass(eq=False)
class DeviceConnection:
    device: str
    socket: DeviceSocket
    capabilities: frozenset[str]
    connected_at: float
    last_seen: float
    pending: dict[str, asyncio.Future[CommandResult]] = field(default_factory=dict)
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    """Set when the manager drops this connection; its session must end."""


class ConnectionManager:
    """At most one live connection per device; a reconnect replaces the old one."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._connections: dict[str, DeviceConnection] = {}

    def get(self, device: str) -> DeviceConnection | None:
        return self._connections.get(device)

    def devices(self) -> list[str]:
        return sorted(self._connections)

    async def connect(
        self, device: str, socket: DeviceSocket, capabilities: frozenset[str]
    ) -> DeviceConnection:
        now = self.clock()
        conn = DeviceConnection(device, socket, capabilities, connected_at=now, last_seen=now)
        previous = self._connections.get(device)
        self._connections[device] = conn
        if previous is not None:
            await self._drop(previous, CloseCode.REPLACED, "Replaced by a newer connection.")
        return conn

    async def disconnect(self, conn: DeviceConnection) -> bool:
        """Forget a connection. Returns False if it was already replaced or removed."""
        current = self._connections.get(conn.device) is conn
        if current:
            del self._connections[conn.device]
        self._fail_pending(conn)
        conn.closed.set()
        return current

    def touch(self, conn: DeviceConnection) -> None:
        conn.last_seen = self.clock()

    async def send(self, conn: DeviceConnection, frame: _Frame) -> None:
        await conn.socket.send_text(encode(frame))

    async def send_command(
        self,
        device: str,
        action: str,
        args: Mapping[str, object],
        *,
        timeout: float,  # noqa: ASYNC109  # expiry raises the domain CommandTimeout
    ) -> CommandResult:
        conn = self._connections.get(device)
        if conn is None:
            raise DeviceNotConnected(f"{device} is not connected.")
        if action not in conn.capabilities:
            raise CapabilityNotDeclared(f"{device} did not declare {action}.")
        command = Command.model_validate({"action": action, "args": dict(args)})
        future: asyncio.Future[CommandResult] = asyncio.get_running_loop().create_future()
        conn.pending[command.id] = future
        try:
            try:
                await self.send(conn, command)
            except Exception as error:
                # A socket that cannot be written to is dead: evict it now rather
                # than leaving a zombie for the heartbeat to find.
                await self._drop(conn, CloseCode.GOING_AWAY, "Send failed.")
                raise DeviceDisconnected(f"{device} disconnected.") from error
            try:
                return await asyncio.wait_for(future, timeout)
            except TimeoutError as error:
                raise CommandTimeout(f"{device} did not answer {action} in time.") from error
        finally:
            conn.pending.pop(command.id, None)

    def resolve(self, conn: DeviceConnection, result: CommandResult) -> bool:
        """Complete a pending command. Only the device it was sent to can answer it."""
        future = conn.pending.get(result.command_id)
        if future is None or future.done():
            return False
        future.set_result(result)
        return True

    async def close_all(self, code: CloseCode = CloseCode.GOING_AWAY) -> None:
        for conn in list(self._connections.values()):
            await self._drop(conn, code, "Zeno is shutting down.")

    async def _drop(self, conn: DeviceConnection, code: CloseCode, reason: str) -> None:
        await self.disconnect(conn)
        with suppress(Exception):  # the socket may already be gone
            await conn.socket.close(code=code, reason=reason)

    @staticmethod
    def _fail_pending(conn: DeviceConnection) -> None:
        for future in conn.pending.values():
            if not future.done():
                future.set_exception(DeviceDisconnected(f"{conn.device} disconnected."))
