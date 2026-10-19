import asyncio
import json

import pytest

from zeno.senses.manager import (
    CapabilityNotDeclared,
    CommandTimeout,
    ConnectionManager,
    DeviceDisconnected,
    DeviceNotConnected,
)
from zeno.senses.protocol import CloseCode, CommandResult, Ping


class FakeSocket:
    def __init__(self, *, broken: bool = False) -> None:
        self.sent: list[dict[str, object]] = []
        self.closed: tuple[int, str | None] | None = None
        self.broken = broken
        self.on_send: asyncio.Event = asyncio.Event()

    async def send_text(self, data: str) -> None:
        if self.broken:
            raise RuntimeError("socket is gone")
        self.sent.append(json.loads(data))
        self.on_send.set()

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = (code, reason)


CAPS = frozenset({"sensor.temperature", "actuator.relay"})


async def test_connect_and_list() -> None:
    manager = ConnectionManager()
    conn = await manager.connect("pi-a", FakeSocket(), CAPS)
    assert manager.devices() == ["pi-a"]
    assert manager.get("pi-a") is conn
    assert conn.capabilities == CAPS


async def test_reconnect_replaces_and_closes_the_old_socket() -> None:
    manager = ConnectionManager()
    old_socket, new_socket = FakeSocket(), FakeSocket()
    old = await manager.connect("pi-a", old_socket, CAPS)
    new = await manager.connect("pi-a", new_socket, CAPS)
    assert old_socket.closed is not None and old_socket.closed[0] == CloseCode.REPLACED
    assert manager.get("pi-a") is new
    # The old socket's cleanup must not evict the new connection.
    assert await manager.disconnect(old) is False
    assert manager.get("pi-a") is new
    assert await manager.disconnect(new) is True
    assert manager.devices() == []


async def test_send_command_round_trip() -> None:
    manager = ConnectionManager()
    socket = FakeSocket()
    conn = await manager.connect("pi-a", socket, CAPS)
    task = asyncio.create_task(
        manager.send_command("pi-a", "actuator.relay", {"on": True}, timeout=1.0)
    )
    await socket.on_send.wait()
    sent = socket.sent[0]
    assert (sent["type"], sent["action"], sent["args"]) == (
        "command",
        "actuator.relay",
        {"on": True},
    )
    assert manager.resolve(conn, CommandResult(command_id=str(sent["id"]), ok=True, detail="on"))
    result = await task
    assert result.ok and result.detail == "on"


async def test_send_command_requires_a_connected_device() -> None:
    with pytest.raises(DeviceNotConnected):
        await ConnectionManager().send_command("pi-x", "actuator.relay", {}, timeout=0.1)


async def test_send_command_requires_a_declared_capability() -> None:
    manager = ConnectionManager()
    socket = FakeSocket()
    await manager.connect("pi-a", socket, CAPS)
    with pytest.raises(CapabilityNotDeclared):
        await manager.send_command("pi-a", "actuator.door_lock", {}, timeout=0.1)
    assert socket.sent == []


async def test_send_command_times_out_and_forgets_the_command() -> None:
    manager = ConnectionManager()
    conn = await manager.connect("pi-a", FakeSocket(), CAPS)
    with pytest.raises(CommandTimeout):
        await manager.send_command("pi-a", "actuator.relay", {}, timeout=0.05)
    assert conn.pending == {}


async def test_disconnect_fails_commands_in_flight() -> None:
    manager = ConnectionManager()
    socket = FakeSocket()
    conn = await manager.connect("pi-a", socket, CAPS)
    task = asyncio.create_task(manager.send_command("pi-a", "actuator.relay", {}, timeout=5))
    await socket.on_send.wait()
    await manager.disconnect(conn)
    with pytest.raises(DeviceDisconnected):
        await task


async def test_a_dead_socket_is_removed_instead_of_lingering() -> None:
    manager = ConnectionManager()
    await manager.connect("pi-a", FakeSocket(broken=True), CAPS)
    with pytest.raises(DeviceDisconnected):
        await manager.send_command("pi-a", "actuator.relay", {}, timeout=1)
    assert manager.devices() == []


async def test_results_only_resolve_their_own_device_commands() -> None:
    manager = ConnectionManager()
    socket = FakeSocket()
    await manager.connect("pi-a", socket, CAPS)
    other = await manager.connect("pi-b", FakeSocket(), CAPS)
    task = asyncio.create_task(manager.send_command("pi-a", "actuator.relay", {}, timeout=0.2))
    await socket.on_send.wait()
    forged = CommandResult(command_id=str(socket.sent[0]["id"]), ok=True)
    assert manager.resolve(other, forged) is False
    with pytest.raises(CommandTimeout):
        await task


async def test_unknown_results_are_ignored() -> None:
    manager = ConnectionManager()
    conn = await manager.connect("pi-a", FakeSocket(), CAPS)
    assert manager.resolve(conn, CommandResult(command_id="nope", ok=True)) is False


async def test_send_frame_and_touch() -> None:
    now = [100.0]
    manager = ConnectionManager(clock=lambda: now[0])
    socket = FakeSocket()
    conn = await manager.connect("pi-a", socket, CAPS)
    assert conn.last_seen == 100.0
    now[0] = 105.0
    manager.touch(conn)
    assert conn.last_seen == 105.0
    await manager.send(conn, Ping())
    assert socket.sent[0]["type"] == "ping"


async def test_close_all() -> None:
    manager = ConnectionManager()
    sockets = [FakeSocket(), FakeSocket()]
    await manager.connect("pi-a", sockets[0], CAPS)
    await manager.connect("pi-b", sockets[1], CAPS)
    await manager.close_all()
    assert manager.devices() == []
    assert all(s.closed is not None and s.closed[0] == CloseCode.GOING_AWAY for s in sockets)
