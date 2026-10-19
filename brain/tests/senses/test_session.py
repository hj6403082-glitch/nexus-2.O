"""DeviceSession against a client that stops responding entirely."""

import asyncio
import json
from typing import Any

import anyio

from zeno.config import Settings
from zeno.senses.auth import DeviceAuth
from zeno.senses.events import EventBus
from zeno.senses.manager import ConnectionManager
from zeno.senses.protocol import CloseCode
from zeno.senses.server import DeviceSession


class StuckSocket:
    """Sends its scripted frames, then never sends (or acknowledges) anything again."""

    def __init__(self, token: str, frames: list[str]) -> None:
        self.headers = {"authorization": f"Bearer {token}"}
        self.frames = frames
        self.sent: list[dict[str, Any]] = []
        self.closed: int | None = None

    async def accept(self) -> None:
        return None

    async def receive(self) -> dict[str, Any]:
        if self.frames:
            return {"type": "websocket.receive", "text": self.frames.pop(0)}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send_text(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = code


HELLO = json.dumps({"v": 1, "id": "h", "type": "hello", "capabilities": []})


async def test_a_replaced_session_ends_even_if_the_old_client_is_stuck() -> None:
    # Heartbeats are slow here, so only the replacement itself can end the session.
    settings = Settings(_env_file=None, heartbeat_interval=30.0, heartbeat_timeout=60.0)
    auth, manager = DeviceAuth(), ConnectionManager()
    token = auth.register("pi-a")
    stuck = StuckSocket(token, [HELLO])
    session = DeviceSession(stuck, "pi-a", settings, auth, manager, EventBus())  # type: ignore[arg-type]
    task = asyncio.create_task(session.run())
    while manager.get("pi-a") is None:  # noqa: ASYNC110  # the session exposes no ready event
        await asyncio.sleep(0.01)

    replacement = StuckSocket(token, [])
    new = await manager.connect("pi-a", replacement, frozenset())

    await asyncio.wait_for(task, timeout=1.0)
    assert stuck.closed == CloseCode.REPLACED
    assert manager.get("pi-a") is new


class LeavingSocket(StuckSocket):
    """Sends hello, then disconnects."""

    async def receive(self) -> dict[str, Any]:
        if self.frames:
            return await super().receive()
        return {"type": "websocket.disconnect", "code": 1000}


async def run_in_scope_cancelled_after(session: DeviceSession, turns: int) -> None:
    """Run the session the way the server does, in a cancel scope that is cancelled
    ``turns`` event-loop turns after it starts."""
    with anyio.CancelScope() as scope:

        async def cancel_later() -> None:
            for _ in range(turns):
                await asyncio.sleep(0)
            scope.cancel()

        canceller = asyncio.create_task(cancel_later())
        try:
            await session.run()
        finally:
            await canceller


async def test_a_session_cancelled_while_closing_stays_cancelled_by_its_caller() -> None:
    # The server (or a test client) cancels a session's cancel scope while the
    # session may still be tidying up its helper tasks. Whatever moment that lands
    # on, the scope must recognise the cancellation as its own and absorb it.
    settings = Settings(_env_file=None, heartbeat_interval=30.0, heartbeat_timeout=60.0)
    for turns in range(12):  # every interleaving of the shutdown, one loop turn apart
        auth, manager = DeviceAuth(), ConnectionManager()
        socket = LeavingSocket(auth.register("pi-a"), [HELLO])
        session = DeviceSession(socket, "pi-a", settings, auth, manager, EventBus())  # type: ignore[arg-type]
        await asyncio.wait_for(run_in_scope_cancelled_after(session, turns), timeout=2.0)
        assert manager.get("pi-a") is None
