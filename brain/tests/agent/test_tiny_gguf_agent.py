"""Integration: the agent on the real llama.cpp backend (tiny random-weight GGUF).

The model's weights are random, so its choices are nonsense and its free-text
fields rarely end before ``max_tokens``. What this proves is the plumbing: the step
grammar compiles and constrains the real sampler, a cut-off step is rejected
cleanly, only registered tools are ever called, nothing mutating runs without
approval, and the run always ends with a result.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from tests.agent.conftest import ASK, Toolbox, drive
from zeno.agent.audit import MemoryAuditLog
from zeno.agent.events import Finished, ToolCall
from zeno.agent.loop import AgentLimits, ReActAgent
from zeno.agent.registry import ToolRegistry
from zeno.config import Settings
from zeno.inference.base import GenerationParams
from zeno.inference.llama_cpp import LlamaCppEngine

CONTROL = re.compile(r"[\x00-\x1f]")


@pytest.fixture
async def engine(tiny_gguf: Path) -> AsyncIterator[LlamaCppEngine]:
    engine = LlamaCppEngine(Settings(_env_file=None, model_path=tiny_gguf, context_size=4096))
    yield engine
    engine.close()


@pytest.mark.parametrize("seed", range(3))
async def test_real_sampler_runs_end_to_end(
    engine: LlamaCppEngine, toolbox: Toolbox, seed: int
) -> None:
    registry = ToolRegistry([toolbox.add, toolbox.set_light])
    audit = MemoryAuditLog()
    agent = ReActAgent(
        engine,
        registry,
        audit=audit,
        limits=AgentLimits(max_steps=3),
        params=GenerationParams(max_tokens=48, temperature=1.0, seed=seed),
    )
    events = await drive(agent, ASK, decide=lambda r: r.deny("test") and None)

    result = events[-1]
    assert isinstance(result, Finished)
    # "error" would mean llama.cpp refused the grammar or the engine failed.
    assert result.outcome in {"answered", "step_limit", "loop_detected"}
    assert all(e.tool in registry for e in events if isinstance(e, ToolCall))
    assert all(name == "add" for name, _ in toolbox.calls)  # set_light was denied
    # Whatever the sampler wrote, cut off or not, the grammar shaped it as JSON.
    for record in audit.records:
        if record.kind == "step_rejected":
            raw = record.data["raw"]
            assert raw.lstrip().startswith("{")
            assert not CONTROL.search(raw)


async def test_the_full_built_in_tool_grammar_compiles_in_llama_cpp(
    engine: LlamaCppEngine, tmp_path: Path
) -> None:
    # Python's LlamaGrammar.from_string is laxer than llama.cpp's parser, so check
    # every built-in tool's schema against the real one, through the engine.
    from zeno.agent.steps import step_grammar
    from zeno.agent.tools import builtin_tools
    from zeno.agent.tools.devices import SensorCache
    from zeno.agent.tools.mqtt import mqtt_tools
    from zeno.agent.tools.network import network_tools
    from zeno.agent.tools.scripts import script_tools
    from zeno.agent.tools.ssh import SshConfig, ssh_tools
    from zeno.agent.tools.ui import ui_tools
    from zeno.agent.tools.web import FetchPolicy, web_tools
    from zeno.memory.episodic import EpisodicMemory
    from zeno.memory.fake import HashEmbedder, InMemoryVectorStore
    from zeno.memory.manager import MemoryManager
    from zeno.memory.semantic import FactMemory
    from zeno.senses.manager import ConnectionManager
    from zeno.senses.mqtt import MqttConfig

    async def nowhere(command: dict[str, object]) -> None:
        return None

    class NoBroker:
        async def publish(self, topic: str, payload: bytes, *, qos: int, retain: bool) -> None:
            return None

    host = {"host": "10.0.0.2", "user": "zeno", "key_file": str(tmp_path / "key")}
    ssh = SshConfig.model_validate(
        {"known_hosts": str(tmp_path / "known"), "hosts": {"pi": host, "nas-1": host}}
    )
    number = {"type": "number", "min": 0, "max": 254, "integer": True, "required": False}
    mqtt = MqttConfig.model_validate(
        {
            "broker": {"host": "127.0.0.1"},
            "read": [{"name": "room.temperature", "topic": "home/room"}],
            "actuators": [
                {
                    "name": "light",
                    "description": "A light.",
                    "topic": "home/light/set",
                    "payload": {
                        "state": {"type": "enum", "values": ["ON", "OFF"]},
                        "level": number,
                        "big": {**number, "max": 5000},
                        "celsius": {"type": "number", "min": 5.5, "max": 30},
                        "away": {"type": "bool", "required": False},
                        "note": {"type": "string", "max_length": 20, "required": False},
                    },
                }
            ],
        }
    )

    store, embedder = InMemoryVectorStore(), HashEmbedder()
    memory = MemoryManager(
        facts=FactMemory(store, embedder), episodes=EpisodicMemory(store, embedder)
    )
    registry = ToolRegistry(
        [
            *builtin_tools(memory=memory, devices=ConnectionManager()),
            *script_tools(tmp_path, timeout=1.0, max_output=100),
            *ui_tools(nowhere),
            *network_tools(),
            *web_tools(search_url="http://127.0.0.1:8888", fetch=FetchPolicy()),
            *ssh_tools(ssh),
            *mqtt_tools(mqtt, NoBroker(), SensorCache()),
        ]
    )
    assert {"ping", "fetch_page", "ssh_run", "actuate_light", "mqtt_read"} <= set(registry.names())
    await engine.load()
    backend = engine._backend  # the real grammar parser lives here
    assert backend is not None
    assert backend.validate_grammar(step_grammar(registry))
