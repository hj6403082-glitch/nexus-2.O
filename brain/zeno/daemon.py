"""ZenoDaemon: boots the pillars in order, serves the API, and shuts down cleanly."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import uvicorn
from fastapi import FastAPI

from zeno.agent.audit import JsonlAuditLog
from zeno.agent.tools import builtin_tools
from zeno.agent.tools.base import Tool
from zeno.agent.tools.devices import SensorCache
from zeno.agent.tools.mqtt import mqtt_tools
from zeno.agent.tools.network import network_tools
from zeno.agent.tools.scripts import script_tools
from zeno.agent.tools.ssh import load_ssh_config, ssh_tools
from zeno.agent.tools.web import FetchPolicy, web_tools
from zeno.api.app import create_api
from zeno.api.auth import load_or_create_token
from zeno.config import Settings
from zeno.inference.base import InferenceEngine
from zeno.inference.llama_cpp import LlamaCppEngine
from zeno.memory.base import Embedder, VectorStore
from zeno.memory.chroma_store import open_persistent_store
from zeno.memory.embedder import LlamaEmbedder
from zeno.memory.episodic import EpisodicMemory
from zeno.memory.manager import MemoryManager
from zeno.memory.semantic import FactMemory
from zeno.orchestrator import Orchestrator
from zeno.senses.auth import DeviceAuth
from zeno.senses.events import EventBus
from zeno.senses.manager import ConnectionManager
from zeno.senses.mqtt import MqttSense, load_mqtt_config

log = logging.getLogger(__name__)

State = Literal["stopped", "starting", "ready", "stopping", "failed"]


class Engine(InferenceEngine, Protocol):
    async def load(self) -> None: ...

    def close(self) -> None: ...


class LoadableEmbedder(Embedder, Protocol):
    async def load(self) -> None: ...

    def close(self) -> None: ...


class BootError(Exception):
    """A pillar failed to start; everything already started was shut down again."""


def default_engine(settings: Settings) -> Engine:
    return LlamaCppEngine(settings)


def default_embedder(settings: Settings) -> LlamaEmbedder:
    # Any GGUF can embed; a dedicated embedding model is better but optional.
    path = settings.embedding_model_path or settings.model_path
    if path is None:
        raise BootError("No model configured. Set ZENO_MODEL_PATH to a .gguf file.")
    return LlamaEmbedder(path, threads=settings.threads)


def default_store(settings: Settings) -> VectorStore:
    return open_persistent_store(settings.memory_dir)


@dataclass
class Services:
    """Everything that exists only while the daemon is running."""

    engine: Engine
    embedder: LoadableEmbedder
    memory: MemoryManager
    orchestrator: Orchestrator
    base_tools: dict[str, Tool[Any]]
    auth: DeviceAuth
    devices: ConnectionManager


class ZenoDaemon:
    def __init__(
        self,
        settings: Settings,
        *,
        engine_factory: Callable[[Settings], Engine] = default_engine,
        embedder_factory: Callable[[Settings], LoadableEmbedder] = default_embedder,
        store_factory: Callable[[Settings], VectorStore] = default_store,
    ) -> None:
        self.settings = settings
        self._engine_factory = engine_factory
        self._embedder_factory = embedder_factory
        self._store_factory = store_factory
        self.state: State = "stopped"
        self.error: str | None = None
        self.api_token = ""
        self.auth = DeviceAuth(settings.devices_file)
        self.devices = ConnectionManager()
        self.bus = EventBus(settings.event_queue_size)
        self.sensors = SensorCache()
        self.mqtt: MqttSense | None = None
        self._services: Services | None = None
        self._cleanups: list[Callable[[], Any]] = []
        self._lifecycle = asyncio.Lock()
        self._server: uvicorn.Server | None = None
        self.app: FastAPI = create_api(self)

    @property
    def services(self) -> Services:
        if self._services is None:
            raise RuntimeError("Zeno is not running.")
        return self._services

    async def start(self) -> None:
        """Boot every pillar, in order, exactly once. Safe to call concurrently."""
        async with self._lifecycle:
            if self.state == "ready":
                return
            self.state, self.error = "starting", None
            try:
                self._services = await self._boot()
            except Exception as error:
                await self._unwind()
                self.state, self.error = "failed", str(error)
                log.error("Zeno failed to start: %s", error)
                raise BootError(str(error)) from error
            self.state = "ready"
            log.info("Zeno is ready.")

    async def _boot(self) -> Services:
        s = self.settings
        self.api_token = await asyncio.to_thread(load_or_create_token, s.api_token_file)

        store = await asyncio.to_thread(self._store_factory, s)  # Pillar 2: ChromaDB
        embedder = self._embedder_factory(s)
        self._cleanups.append(embedder.close)
        await embedder.load()
        memory = MemoryManager(
            facts=FactMemory(store, embedder),
            episodes=EpisodicMemory(store, embedder, half_life_days=s.episode_half_life_days),
            min_similarity=s.memory_min_similarity,
        )

        engine = self._engine_factory(s)  # Pillar 1: the chat model
        self._cleanups.append(engine.close)
        await engine.load()

        await self.bus.start()  # Pillar 3: devices
        self._cleanups.append(self.bus.stop)
        self._cleanups.append(self.devices.close_all)
        self._cleanups.append(self.sensors.attach(self.bus))

        tools = [  # Pillar 4: the agent's tools
            *builtin_tools(
                memory=memory,
                devices=self.devices,
                sensors=self.sensors,
                command_timeout=s.command_timeout,
            ),
            *script_tools(s.scripts_dir, timeout=s.script_timeout, max_output=s.script_max_output),
            *await self._outbound_tools(),
        ]
        orchestrator = Orchestrator(
            engine=engine,
            memory=memory,
            audit=JsonlAuditLog(s.audit_log_path),
            settings=s,
            base_tools=tools,
        )
        return Services(
            engine=engine,
            embedder=embedder,
            memory=memory,
            orchestrator=orchestrator,
            base_tools={t.name: t for t in tools},
            auth=self.auth,
            devices=self.devices,
        )

    async def _outbound_tools(self) -> list[Tool[Any]]:
        """Phase 2 tools that reach beyond this PC; each needs its own configuration."""
        s = self.settings
        tools: list[Tool[Any]] = network_tools() if s.network_tools else []
        fetch = None
        if s.web_fetch:
            fetch = FetchPolicy(
                allow_lan=s.web_fetch_allow_lan,
                max_bytes=s.web_fetch_max_bytes,
                max_chars=s.agent_max_observation_chars,
                timeout=s.web_fetch_timeout,
            )
        tools += web_tools(search_url=s.web_search_url, fetch=fetch)
        ssh = await asyncio.to_thread(load_ssh_config, s.ssh_hosts_file)
        if ssh is not None:
            tools += ssh_tools(
                ssh, command_timeout=s.ssh_command_timeout, max_output=s.ssh_max_output
            )
        mqtt = await asyncio.to_thread(load_mqtt_config, s.mqtt_file)
        if mqtt is not None:
            self.mqtt = MqttSense(mqtt, self.bus)
            self._cleanups.append(self._stop_mqtt)
            await self.mqtt.start()  # connects in the background; boot does not wait
            tools += mqtt_tools(mqtt, self.mqtt, self.sensors)
        return tools

    async def _stop_mqtt(self) -> None:
        if self.mqtt is not None:
            await self.mqtt.stop()
            self.mqtt = None

    async def stop(self) -> None:
        """Close device connections, stop the bus and free the models. Idempotent."""
        async with self._lifecycle:
            if self.state in ("stopped", "failed"):
                return
            self.state = "stopping"
            await self._unwind()
            self._services = None
            self.state = "stopped"
            log.info("Zeno stopped.")

    async def _unwind(self) -> None:
        while self._cleanups:
            cleanup = self._cleanups.pop()
            try:
                result = cleanup()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                log.exception("Error while shutting down")

    async def serve(self) -> None:
        """Run the API with uvicorn. The app's lifespan boots the pillars before the
        socket is bound, and shuts them down after it closes."""
        config = uvicorn.Config(
            self.app,
            host=self.settings.senses_host,
            port=self.settings.senses_port,
            ws_max_size=self.settings.max_frame_bytes * 2,
            lifespan="on",
            server_header=False,
            proxy_headers=False,
            log_level="info",
        )
        self._server = uvicorn.Server(config)
        await self._server.serve()

    async def wait_until_serving(self) -> int:
        """Wait for :meth:`serve` to accept connections; return the bound port."""
        # uvicorn exposes no started event, so poll.
        while self._server is None or not self._server.started:
            if self.state == "failed":
                raise BootError(self.error or "Zeno failed to start.")
            await asyncio.sleep(0.02)
        sockets = [sock for server in self._server.servers for sock in server.sockets]
        port: int = sockets[0].getsockname()[1]
        return port

    def shutdown(self) -> None:
        """Ask a running :meth:`serve` to stop."""
        if self._server is not None:
            self._server.should_exit = True
