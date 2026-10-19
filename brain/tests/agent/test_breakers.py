"""Circuit breakers: step limit, loop detection, timeouts and tool errors."""

import time

import pytest

from tests.agent.conftest import Toolbox, act, drive, final, finished, make_agent
from zeno.agent.audit import MemoryAuditLog
from zeno.agent.events import ApprovalRequired, Observation
from zeno.agent.loop import AgentLimits
from zeno.agent.registry import ToolRegistry
from zeno.agent.tools.base import Risk, ToolArgs, tool


async def test_stops_at_the_step_limit(
    registry: ToolRegistry, audit: MemoryAuditLog, toolbox: Toolbox
) -> None:
    script = [act("add", a=i, b=1) for i in range(10)]
    agent, engine = make_agent(script, registry, audit)
    events = await drive(agent)
    result = finished(events)
    assert result.outcome == "step_limit"
    assert result.steps == 5
    assert "5 steps" in result.answer
    assert len(engine.calls) == 5
    assert len(toolbox.calls) == 5


async def test_step_limit_is_configurable(registry: ToolRegistry, audit: MemoryAuditLog) -> None:
    agent, engine = make_agent(
        [act("add", a=i, b=1) for i in range(5)], registry, audit, max_steps=2
    )
    assert finished(await drive(agent)).outcome == "step_limit"
    assert len(engine.calls) == 2


async def test_a_final_answer_on_the_last_step_still_counts(
    registry: ToolRegistry, audit: MemoryAuditLog
) -> None:
    agent, _ = make_agent([act("add", a=1, b=1), final("2")], registry, audit, max_steps=2)
    assert finished(await drive(agent)).outcome == "answered"


async def test_repeating_the_same_call_is_a_loop(
    registry: ToolRegistry, audit: MemoryAuditLog, toolbox: Toolbox
) -> None:
    agent, engine = make_agent([act("add", a=1, b=2)] * 3 + [final("3")], registry, audit)
    events = await drive(agent)
    result = finished(events)
    assert result.outcome == "loop_detected"
    assert "add" in result.answer
    assert len(toolbox.calls) == 2  # the third identical call never ran
    assert len(engine.calls) == 3


async def test_loops_are_detected_when_calls_alternate(
    registry: ToolRegistry, audit: MemoryAuditLog, toolbox: Toolbox
) -> None:
    a, b = act("add", a=1, b=2), act("add", a=3, b=4)
    agent, _ = make_agent([a, b, a, b, a, final("x")], registry, audit, max_steps=6)
    assert finished(await drive(agent)).outcome == "loop_detected"
    assert len(toolbox.calls) == 4


async def test_argument_order_does_not_hide_a_loop(
    registry: ToolRegistry, audit: MemoryAuditLog
) -> None:
    first = '{"thought": "t", "action": {"tool": "add", "args": {"a": 1, "b": 2}}}'
    swapped = '{"thought": "t", "action": {"tool": "add", "args": {"b": 2, "a": 1}}}'
    agent, _ = make_agent([first, swapped, first, final("x")], registry, audit)
    assert finished(await drive(agent)).outcome == "loop_detected"


class OptionArgs(ToolArgs):
    options: dict[str, int]


async def test_key_order_inside_nested_arguments_does_not_hide_a_loop(
    audit: MemoryAuditLog,
) -> None:
    @tool(risk=Risk.READ_ONLY)
    async def configure(args: OptionArgs) -> str:
        """Apply options."""
        return "ok"

    first = act("configure", options={"x": 1, "y": 2})
    swapped = act("configure", options={"y": 2, "x": 1})
    agent, _ = make_agent([first, swapped, first, final("x")], ToolRegistry([configure]), audit)
    assert finished(await drive(agent)).outcome == "loop_detected"


async def test_different_arguments_are_not_a_loop(
    registry: ToolRegistry, audit: MemoryAuditLog
) -> None:
    script = [act("add", a=i, b=i) for i in range(4)] + [final("done")]
    agent, _ = make_agent(script, registry, audit)
    assert finished(await drive(agent)).outcome == "answered"


async def test_repeated_denied_requests_stop_without_asking_again(
    registry: ToolRegistry, audit: MemoryAuditLog, toolbox: Toolbox
) -> None:
    light = act("set_light", room="hall", on=True)
    agent, _ = make_agent([light] * 3 + [final("x")], registry, audit)
    events = await drive(agent, decide=lambda r: r.deny() and None)
    assert sum(isinstance(e, ApprovalRequired) for e in events) == 2
    assert finished(events).outcome == "loop_detected"
    assert toolbox.calls == []


async def test_a_slow_tool_times_out_and_the_run_continues(
    registry: ToolRegistry, audit: MemoryAuditLog
) -> None:
    agent, engine = make_agent([act("slow", seconds=5), final("It was too slow.")], registry, audit)
    started = time.monotonic()
    events = await drive(agent)
    assert time.monotonic() - started < 2
    observation = next(e for e in events if isinstance(e, Observation))
    assert observation.ok is False
    assert "timed out" in observation.content
    assert "timed out" in engine.calls[1][0][-1].content
    assert finished(events).outcome == "answered"


async def test_a_failing_tool_becomes_an_error_observation(
    registry: ToolRegistry, audit: MemoryAuditLog
) -> None:
    agent, _ = make_agent([act("explode", a=1, b=1), final("The sensor failed.")], registry, audit)
    events = await drive(agent)
    observation = next(e for e in events if isinstance(e, Observation))
    assert observation.ok is False
    assert "RuntimeError" in observation.content
    assert "the sensor caught fire" in observation.content
    assert finished(events).answer == "The sensor failed."


@pytest.mark.parametrize(
    "limits",
    [
        {"max_steps": 0},
        {"max_identical_calls": 0},
        {"approval_timeout": 0},
        {"max_observation_chars": 0},
    ],
)
def test_limits_must_be_positive(limits: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        AgentLimits(**limits)  # type: ignore[arg-type]


def test_default_limits() -> None:
    limits = AgentLimits()
    assert limits.max_steps == 5
    assert limits.max_identical_calls == 2
