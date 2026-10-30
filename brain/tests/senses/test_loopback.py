"""v1 decision: the senses server only ever listens on this PC."""

import asyncio
import json
from typing import Any

import pytest
import uvicorn
from pydantic import ValidationError
from websockets.asyncio.client import connect

from zeno.config import Settings
from zeno.senses.auth import DeviceAuth
from zeno.senses.server import create_app, server_config


def test_defaults_to_loopback() -> None:
    settings = Settings(_env_file=None)
    assert settings.senses_host == "127.0.0.1"
    assert settings.senses_port == 8765


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_accepts_loopback_hosts(host: str) -> None:
    assert Settings(_env_file=None, senses_host=host).senses_host == host


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "10.0.0.5", "zeno.local"])  # noqa: S104
def test_refuses_to_listen_beyond_this_pc(host: str) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(_env_file=None, senses_host=host)


def test_server_config_uses_the_configured_loopback_host() -> None:
    settings = Settings(_env_file=None)
    config = server_config(settings, create_app(settings, auth=DeviceAuth()))
    assert (config.host, config.port) == ("127.0.0.1", 8765)


async def test_real_server_binds_to_127_0_0_1_and_talks_websockets() -> None:
    settings = Settings(_env_file=None, senses_port=0, heartbeat_interval=5.0)
    auth = DeviceAuth()
    token = auth.register("pi-real")
    server = uvicorn.Server(server_config(settings, create_app(settings, auth=auth)))
    task = asyncio.create_task(server.serve())
    try:
        while not server.started:  # noqa: ASYNC110  # uvicorn exposes no started event
            await asyncio.sleep(0.01)
        sockets: list[Any] = [s for srv in server.servers for s in srv.sockets]
        hosts = {s.getsockname()[0] for s in sockets}
        assert hosts == {"127.0.0.1"}
        port = sockets[0].getsockname()[1]

        url = f"ws://127.0.0.1:{port}/v1/devices/pi-real/ws"
        async with connect(url, additional_headers={"Authorization": f"Bearer {token}"}) as ws:
            await ws.send(json.dumps({"v": 1, "id": "h", "type": "hello", "capabilities": []}))
            assert json.loads(await ws.recv())["type"] == "welcome"
            await ws.send(json.dumps({"v": 1, "id": "p", "type": "ping"}))
            assert json.loads(await ws.recv()) == {"v": 1, "id": "p", "type": "pong"}
    finally:
        server.should_exit = True
        await task
