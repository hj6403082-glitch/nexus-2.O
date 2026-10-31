"""ZenoDaemon: boots every pillar in order, exactly once, and shuts down cleanly."""

import asyncio
import os
import stat
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

from tests.api.conftest import brain_settings, wait_until
from tests.senses.conftest import hello, receive, send
from zeno.agent.tools.devices import SensorArgs
from zeno.daemon import BootError, ZenoDaemon, default_embedder
from zeno.inference.base import ModelNotFoundError
from zeno.inference.fake import ScriptedEngine
from zeno.memory.embedder import LlamaEmbedder
from zeno.memory.fake import HashEmbedder, InMemoryVectorStore


class Log(list[str]):
    pass


class RecordingEngine(ScriptedEngine):
    def __init__(self, log: Log, *, fail: Exception | None = None) -> None:
        super().__init__([])
        self.log, self.fail = log, fail
        self.release = asyncio.Event()
        self.release.set()

    async def load(self) -> None:
        await self.release.wait()
        self.log.append("engine.load")
        if self.fail is not None:
            raise self.fail

    def close(self) -> None:
        self.log.append("engine.close")


class RecordingEmbedder(HashEmbedder):
    def __init__(self, log: Log) -> None:
        super().__init__()
        self.log = log

    async def load(self) -> None:
        self.log.append("embedder.load")

    def close(self) -> None:
        self.log.append("embedder.close")


def make_daemon(
    tmp_path: Path, log: Log, engine: RecordingEngine | None = None, **overrides: Any
) -> tuple[ZenoDaemon, RecordingEngine]:
    engine = engine or RecordingEngine(log)

    def open_store(_: Any) -> InMemoryVectorStore:
        log.append("store.open")
        return InMemoryVectorStore()

    daemon = ZenoDaemon(
        brain_settings(tmp_path, **overrides),
        engine_factory=lambda _: engine,
        embedder_factory=lambda _: RecordingEmbedder(log),
        store_factory=open_store,
    )
    return daemon, engine


def test_boots_memory_then_models_then_serves(tmp_path: Path) -> None:
    log = Log()
    daemon, _ = make_daemon(tmp_path, log)
    assert daemon.state == "stopped"
    with TestClient(daemon.app) as client:
        assert daemon.state == "ready"
        assert log == ["store.open", "embedder.load", "engine.load"]
        assert client.get("/v1/status").json()["state"] == "ready"
    assert daemon.state == "stopped"
    assert log[3:] == ["engine.close", "embedder.close"]


async def test_concurrent_starts_boot_once(tmp_path: Path) -> None:
    log = Log()
    daemon, _ = make_daemon(tmp_path, log)
    await asyncio.gather(daemon.start(), daemon.start(), daemon.start())
    assert log == ["store.open", "embedder.load", "engine.load"]
    await asyncio.gather(daemon.stop(), daemon.stop())
    assert log.count("engine.close") == 1


async def test_status_says_starting_until_every_pillar_is_up(tmp_path: Path) -> None:
    log = Log()
    engine = RecordingEngine(log)
    engine.release.clear()  # the model "loads" until released
    daemon, _ = make_daemon(tmp_path, log, engine)
    booting = asyncio.create_task(daemon.start())
    transport = httpx.ASGITransport(app=daemon.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://zeno") as client:
        while "embedder.load" not in log:  # noqa: ASYNC110  # boot exposes no progress event
            await asyncio.sleep(0.01)
        assert daemon.state == "starting"
        assert (await client.get("/v1/status")).json()["state"] == "starting"
        engine.release.set()
        await booting
        assert (await client.get("/v1/status")).json()["state"] == "ready"
    await daemon.stop()


async def test_a_failed_boot_unwinds_and_says_why(tmp_path: Path) -> None:
    log = Log()
    engine = RecordingEngine(log, fail=ModelNotFoundError("Model file not found: x.gguf"))
    daemon, _ = make_daemon(tmp_path, log, engine)
    with pytest.raises(BootError, match="Model file not found"):
        await daemon.start()
    assert daemon.state == "failed"
    assert daemon.error is not None and "Model file not found" in daemon.error
    # What had started is closed again, newest first.
    assert log == ["store.open", "embedder.load", "engine.load", "engine.close", "embedder.close"]
    transport = httpx.ASGITransport(app=daemon.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://zeno") as client:
        status = (await client.get("/v1/status")).json()
    assert status["state"] == "failed"
    assert "Model file not found" in status["message"]


def test_the_server_never_starts_if_boot_fails(tmp_path: Path) -> None:
    log = Log()
    daemon, _ = make_daemon(tmp_path, log, RecordingEngine(log, fail=ModelNotFoundError("nope")))
    with pytest.raises(BootError), TestClient(daemon.app):
        pass


async def test_stop_before_start_is_harmless(tmp_path: Path) -> None:
    daemon, _ = make_daemon(tmp_path, Log())
    await daemon.stop()
    assert daemon.state == "stopped"


def test_devices_connect_through_the_daemon_and_feed_the_tools(tmp_path: Path) -> None:
    log = Log()
    daemon, _ = make_daemon(tmp_path, log)
    with TestClient(daemon.app) as client:
        token = daemon.services.auth.register("pi-a")
        with client.websocket_connect(
            "/v1/devices/pi-a/ws", headers={"Authorization": f"Bearer {token}"}
        ) as device:
            assert hello(device, ["sensor.temperature"])["type"] == "welcome"
            send(device, type="sensor", sensor="sensor.temperature", value=21.5, unit="C")
            read_sensor = daemon.services.base_tools["read_sensor"]

            def reading() -> str:
                args = SensorArgs(device="pi-a", sensor="sensor.temperature")
                text: str = client.portal.call(read_sensor.invoke, args)  # type: ignore[union-attr]
                return text

            wait_until(lambda: "21.5" in reading())
            assert client.get("/v1/status").json()["devices"] == ["pi-a"]


def test_shutdown_closes_device_connections(tmp_path: Path) -> None:
    from starlette.websockets import WebSocketDisconnect

    daemon, _ = make_daemon(tmp_path, Log())
    with TestClient(daemon.app) as client:
        token = daemon.services.auth.register("pi-a")
        with client.websocket_connect(
            "/v1/devices/pi-a/ws", headers={"Authorization": f"Bearer {token}"}
        ) as device:
            hello(device)
            client.portal.call(daemon.stop)  # type: ignore[union-attr]
            with pytest.raises(WebSocketDisconnect) as closed:
                while True:
                    receive(device)
    assert closed.value.code == 1001
    assert daemon.state == "stopped"


async def test_the_api_token_is_private_and_survives_restarts(tmp_path: Path) -> None:
    daemon, _ = make_daemon(tmp_path, Log())
    await daemon.start()
    token = daemon.api_token
    await daemon.stop()
    path = daemon.settings.api_token_file
    assert path.read_text(encoding="utf-8").strip() == token
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    again, _ = make_daemon(tmp_path, Log())
    await again.start()
    assert again.api_token == token
    await again.stop()


def test_embeddings_fall_back_to_the_chat_model(tmp_path: Path) -> None:
    chat = tmp_path / "chat.gguf"
    embed = tmp_path / "embed.gguf"
    fallback = default_embedder(brain_settings(tmp_path, model_path=chat))
    dedicated = default_embedder(
        brain_settings(tmp_path, model_path=chat, embedding_model_path=embed)
    )
    assert isinstance(fallback, LlamaEmbedder) and fallback.model_path == chat
    assert isinstance(dedicated, LlamaEmbedder) and dedicated.model_path == embed


def test_chat_is_refused_until_the_brain_is_ready(tmp_path: Path) -> None:
    from starlette.websockets import WebSocketDisconnect

    daemon, _ = make_daemon(tmp_path, Log())
    daemon.api_token = "known-token"  # noqa: S105  # as after the first boot step
    client = TestClient(daemon.app)  # not entered: the lifespan (boot) never runs
    with (
        pytest.raises(WebSocketDisconnect) as refused,
        client.websocket_connect("/v1/chat/ws", headers={"Authorization": "Bearer known-token"}),
    ):
        pass
    assert refused.value.code == 1013  # try again later


def test_wake_word_listener_starts_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = Log()
    daemon, _ = make_daemon(tmp_path, log, wakeword=True)
    started: list[str] = []

    class FakeListener:
        def start(self, loop: Any = None) -> None:
            started.append("start")

        def stop(self) -> None:
            started.append("stop")

    monkeypatch.setattr("zeno.daemon.sys.platform", "win32")
    monkeypatch.setattr(
        "zeno.senses.audio_listener.build_listener", lambda s, b, **kw: FakeListener()
    )
    with TestClient(daemon.app):
        assert started == ["start"]
    assert started == ["start", "stop"]


def test_wake_word_listener_is_skipped_off_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = Log()
    daemon, _ = make_daemon(tmp_path, log, wakeword=True)
    monkeypatch.setattr("zeno.daemon.sys.platform", "linux")
    with TestClient(daemon.app):
        assert daemon.wake is None


def test_wake_word_can_be_turned_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = Log()
    daemon, _ = make_daemon(tmp_path, log, wakeword=False)
    monkeypatch.setattr("zeno.daemon.sys.platform", "win32")
    with TestClient(daemon.app):
        assert daemon.wake is None
