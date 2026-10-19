import json
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient, WebSocketTestSession

from zeno.config import Settings
from zeno.daemon import ZenoDaemon
from zeno.inference.fake import ScriptedEngine
from zeno.memory.fake import HashEmbedder, InMemoryVectorStore


def brain_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "model_path": tmp_path / "model.gguf",
        "memory_dir": tmp_path / "memory",
        "devices_file": tmp_path / "devices.json",
        "audit_log_path": tmp_path / "audit" / "agent.jsonl",
        "api_token_file": tmp_path / "api-token",
        "scripts_dir": tmp_path / "scripts",
        "heartbeat_interval": 0.2,
        "heartbeat_timeout": 1.0,
        "memory_min_similarity": 0.2,
        **overrides,
    }
    return Settings(_env_file=None, **values)


@dataclass
class Brain:
    daemon: ZenoDaemon
    client: TestClient
    engine: ScriptedEngine
    sockets: list[Any] = field(default_factory=list)

    @property
    def token(self) -> str:
        return self.daemon.api_token

    def chat(self, *, token: str | None = None, headers: dict[str, str] | None = None) -> Any:
        token = self.token if token is None else token
        return self.client.websocket_connect(
            "/v1/chat/ws", headers={"Authorization": f"Bearer {token}", **(headers or {})}
        )

    def run(self, func: Callable[..., Any], *args: Any) -> Any:
        """Call an async function on the app's own event loop and return its result."""
        return self.client.portal.call(func, *args)  # type: ignore[union-attr]


@pytest.fixture
def make_brain(tmp_path: Path) -> Iterator[Callable[..., Brain]]:
    brains: list[Brain] = []

    def build(responses: Sequence[str] = (), **overrides: Any) -> Brain:
        engine = ScriptedEngine(responses)
        daemon = ZenoDaemon(
            brain_settings(tmp_path, **overrides),
            engine_factory=lambda _: engine,
            embedder_factory=lambda _: HashEmbedder(),
            store_factory=lambda _: InMemoryVectorStore(),
        )
        client = TestClient(daemon.app)
        client.__enter__()
        brains.append(Brain(daemon, client, engine))
        return brains[-1]

    yield build
    for brain in brains:
        for ws in brain.sockets:
            ws.__exit__(None, None, None)
        brain.client.__exit__(None, None, None)


def send(ws: WebSocketTestSession, **frame: Any) -> None:
    ws.send_text(json.dumps(frame))


def receive(ws: WebSocketTestSession) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(ws.receive_text())
    return data


def connect(brain: Brain, **kwargs: Any) -> Any:
    """Open a chat socket and consume its ready frame."""
    ws = brain.chat(**kwargs).__enter__()
    brain.sockets.append(ws)  # closed when the test ends
    ready = receive(ws)
    assert ready["type"] == "ready"
    return ws


Decide = Callable[[dict[str, Any]], dict[str, Any] | None]


def turn(
    ws: WebSocketTestSession, text: str, *, turn_id: str = "t1", decide: Decide | None = None
) -> list[dict[str, Any]]:
    """Send one chat message and collect frames until its ``done`` frame."""
    send(ws, type="chat", id=turn_id, text=text)
    frames = []
    while True:
        frame = receive(ws)
        frames.append(frame)
        if frame["type"] == "approval_required" and decide is not None:
            answer = decide(frame)
            if answer is not None:
                send(ws, **answer)
        if frame["type"] == "done" and frame.get("turn") == turn_id:
            return frames


def approve(frame: dict[str, Any]) -> dict[str, Any]:
    return {"type": "approval", "request_id": frame["request_id"], "approved": True}


def deny(reason: str = "") -> Decide:
    def answer(frame: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "approval",
            "request_id": frame["request_id"],
            "approved": False,
            "reason": reason,
        }

    return answer


def kinds(frames: Sequence[dict[str, Any]]) -> list[str]:
    return [f["type"] for f in frames]


def wait_until(condition: Callable[[], bool], limit: float = 3.0) -> None:
    deadline = time.monotonic() + limit
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)
