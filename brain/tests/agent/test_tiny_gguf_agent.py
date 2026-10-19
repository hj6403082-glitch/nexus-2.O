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
