import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from starlette.testclient import TestClient, WebSocketTestSession

from zeno.config import Settings
from zeno.senses.auth import DeviceAuth
from zeno.senses.events import DeviceEvent
from zeno.senses.server import create_app

CAPS = ["sensor.temperature", "telemetry.system", "actuator.relay"]


@dataclass
class Harness:
    client: TestClient
    auth: DeviceAuth
    tokens: dict[str, str]
    events: list[DeviceEvent] = field(default_factory=list)

    def connect(
        self,
        device: str = "pi-a",
        *,
        token: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        token = self.tokens.get(device, "") if token is None else token
        return self.client.websocket_connect(
            f"/v1/devices/{device}/ws",
            headers={"Authorization": f"Bearer {token}", **(headers or {})},
        )

    @property
    def manager(self) -> Any:
        return self.client.app.state.manager  # type: ignore[attr-defined]


def send(ws: WebSocketTestSession, **fields: Any) -> None:
    ws.send_text(json.dumps({"v": 1, "id": fields.pop("id", "f-test"), **fields}))


def receive(ws: WebSocketTestSession) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(ws.receive_text())
    return data


def hello(ws: WebSocketTestSession, capabilities: list[str] | None = None) -> dict[str, Any]:
    send(ws, type="hello", capabilities=CAPS if capabilities is None else capabilities)
    return receive(ws)


def wait_until(condition: Callable[[], bool], limit: float = 3.0) -> None:
    deadline = time.monotonic() + limit
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)


def fast_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "heartbeat_interval": 0.05,
        "heartbeat_timeout": 0.3,
        "hello_timeout": 0.3,
        "command_timeout": 1.0,
        "max_frame_bytes": 2048,
        "max_invalid_frames": 3,
        **overrides,
    }
    return Settings(_env_file=None, **values)


@pytest.fixture
def make_harness() -> Iterator[Callable[..., Harness]]:
    clients: list[TestClient] = []

    def build(**overrides: Any) -> Harness:
        auth = DeviceAuth()
        tokens = {d: auth.register(d) for d in ("pi-a", "pi-b")}
        app = create_app(fast_settings(**overrides), auth=auth)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        harness = Harness(client, auth, tokens)

        async def record(event: DeviceEvent) -> None:
            harness.events.append(event)

        app.state.bus.subscribe(record)
        return harness

    yield build
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def harness(make_harness: Callable[..., Harness]) -> Harness:
    return make_harness()
