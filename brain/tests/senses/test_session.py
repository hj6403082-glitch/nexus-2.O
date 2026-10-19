"""DeviceSession against a client that stops responding entirely."""

import asyncio
import json
from typing import Any

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
