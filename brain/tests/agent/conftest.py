import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import pytest
from pydantic import Field

from zeno.agent.audit import MemoryAuditLog
from zeno.agent.events import AgentEvent, ApprovalRequired, Finished
from zeno.agent.loop import AgentLimits, ReActAgent
from zeno.agent.policy import ApprovalRequest
from zeno.agent.registry import ToolRegistry
from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool
from zeno.inference.base import ChatMessage
from zeno.inference.fake import ScriptedEngine

ASK = [ChatMessage("system", "You are Zeno."), ChatMessage("user", "What is 2 + 3?")]


class AddArgs(ToolArgs):
    a: int
    b: int


class LightArgs(ToolArgs):
    room: str = Field(min_length=1, max_length=32)
    on: bool


class SleepArgs(ToolArgs):
    seconds: float


class Toolbox:
    """Test tools that record what they were called with."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

        @tool(risk=Risk.READ_ONLY, timeout=1.0)
        async def add(args: AddArgs) -> str:
            """Add two integers."""
            self.calls.append(("add", args.model_dump()))
            return str(args.a + args.b)

        @tool(risk=Risk.MUTATING, timeout=1.0)
        async def set_light(args: LightArgs) -> str:
            """Turn a room's light on or off."""
            self.calls.append(("set_light", args.model_dump()))
            return f"{args.room} light is {'on' if args.on else 'off'}"

        @tool(risk=Risk.READ_ONLY, timeout=0.05)
        async def slow(args: SleepArgs) -> str:
            """Wait, then answer (used to test timeouts)."""
            await asyncio.sleep(args.seconds)
            return "done"

        @tool(risk=Risk.READ_ONLY, timeout=1.0)
        async def explode(args: AddArgs) -> str:
            """Always fails (used to test error handling)."""
            raise RuntimeError("the sensor caught fire")

        self.add, self.set_light, self.slow, self.explode = add, set_light, slow, explode

    def all(self) -> list[Tool]:
        return [self.add, self.set_light, self.slow, self.explode]


@pytest.fixture
def toolbox() -> Toolbox:
    return Toolbox()


@pytest.fixture
def registry(toolbox: Toolbox) -> ToolRegistry:
    return ToolRegistry(toolbox.all())


@pytest.fixture
def audit() -> MemoryAuditLog:
    return MemoryAuditLog()


def act(tool_name: str, thought: str = "I should use a tool.", **args: Any) -> str:
    return json.dumps({"thought": thought, "action": {"tool": tool_name, "args": args}})


def final(answer: str, thought: str = "I know the answer.") -> str:
    return json.dumps({"thought": thought, "final": answer})


def make_agent(
    responses: Sequence[str],
    registry: ToolRegistry,
    audit: MemoryAuditLog,
    **limits: Any,
) -> tuple[ReActAgent, ScriptedEngine]:
    engine = ScriptedEngine(responses)
    return ReActAgent(engine, registry, audit=audit, limits=AgentLimits(**limits)), engine


Decide = Callable[[ApprovalRequest], Awaitable[None] | None]


async def drive(
    agent: ReActAgent,
    messages: Sequence[ChatMessage] = ASK,
    decide: Decide | None = None,
) -> list[AgentEvent]:
    """Run the agent to completion, answering approval requests with ``decide``."""
    events: list[AgentEvent] = []
    async for event in agent.run(messages):
        events.append(event)
        if isinstance(event, ApprovalRequired) and decide is not None:
            outcome = decide(event.request)
            if outcome is not None:
                await outcome
    return events


def finished(events: Sequence[AgentEvent]) -> Finished:
    last = events[-1]
    assert isinstance(last, Finished)
    return last
