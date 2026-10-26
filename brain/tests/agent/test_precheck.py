"""A tool's precheck refuses a call before the owner is asked, with a reason the model sees."""

import asyncio

import pytest

from tests.agent.conftest import AddArgs, Toolbox, act, drive, final, finished, make_agent
from zeno.agent import loop
from zeno.agent.audit import MemoryAuditLog
from zeno.agent.events import ApprovalRequired, Observation
from zeno.agent.policy import ApprovalRequest
from zeno.agent.registry import ToolRegistry
from zeno.agent.tools.base import Risk, Tool, tool


def guarded(calls: list[int]) -> Tool[AddArgs]:
    def precheck(args: AddArgs) -> str | None:
        return "negative numbers are refused" if args.a < 0 else None

    @tool(risk=Risk.MUTATING, timeout=1.0, precheck=precheck)
    async def careful_add(args: AddArgs) -> str:
        """Add two integers, carefully."""
        calls.append(args.a + args.b)
        return str(args.a + args.b)

    return careful_add


async def test_a_refused_call_never_reaches_the_owner_or_runs(audit: MemoryAuditLog) -> None:
    calls: list[int] = []
    asked: list[ApprovalRequest] = []
    agent, _ = make_agent(
        [act("careful_add", a=-1, b=2), final("I can't do that.")],
        ToolRegistry([guarded(calls)]),
        audit,
    )

    def decide(request: ApprovalRequest) -> None:
        asked.append(request)
        request.approve()

    events = await drive(agent, decide=decide)
    assert calls == [] and asked == []
    assert not any(isinstance(e, ApprovalRequired) for e in events)
    observation = next(e for e in events if isinstance(e, Observation))
    assert not observation.ok
    assert "Refused before asking the owner: negative numbers are refused" in observation.content
    assert finished(events).outcome == "answered"
    assert [r.kind for r in audit.records].count("refused") == 1


async def test_an_accepted_call_still_needs_approval(audit: MemoryAuditLog) -> None:
    calls: list[int] = []
    agent, _ = make_agent(
        [act("careful_add", a=1, b=2), final("3.")], ToolRegistry([guarded(calls)]), audit
    )

    def approve(request: ApprovalRequest) -> None:
        request.approve()

    events = await drive(agent, decide=approve)
    assert any(isinstance(e, ApprovalRequired) for e in events)
    assert calls == [3]


def test_tools_have_no_precheck_by_default(toolbox: Toolbox) -> None:
    assert toolbox.add.precheck is None


async def test_a_precheck_that_fails_refuses(audit: MemoryAuditLog) -> None:
    def broken(args: AddArgs) -> str | None:
        raise RuntimeError("bug")

    calls: list[int] = []

    @tool(risk=Risk.READ_ONLY, timeout=1.0, precheck=broken)
    async def add_checked(args: AddArgs) -> str:
        """Add two integers."""
        calls.append(1)
        return "3"

    agent, _ = make_agent(
        [act("add_checked", a=1, b=2), final("Hm.")], ToolRegistry([add_checked]), audit
    )
    events = await drive(agent)
    observation = next(e for e in events if isinstance(e, Observation))
    assert not observation.ok and "could not be checked" in observation.content
    assert calls == []


def approve(request: ApprovalRequest) -> None:
    request.approve()


def async_guarded(calls: list[int], *, delay: float = 0.0) -> Tool[AddArgs]:
    async def precheck(args: AddArgs) -> str | None:
        await asyncio.sleep(delay)
        return "negative numbers are refused" if args.a < 0 else None

    @tool(risk=Risk.MUTATING, timeout=1.0, precheck=precheck)
    async def careful_add(args: AddArgs) -> str:
        """Add two integers, carefully."""
        calls.append(args.a + args.b)
        return str(args.a + args.b)

    return careful_add


async def test_an_async_precheck_is_awaited(audit: MemoryAuditLog) -> None:
    calls: list[int] = []
    agent, _ = make_agent(
        [act("careful_add", a=-1, b=2), final("No.")], ToolRegistry([async_guarded(calls)]), audit
    )
    events = await drive(agent, decide=approve)
    observation = next(e for e in events if isinstance(e, Observation))
    assert "Refused before asking the owner: negative numbers are refused" in observation.content
    assert calls == []


async def test_a_precheck_that_hangs_refuses(
    audit: MemoryAuditLog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loop, "PRECHECK_TIMEOUT", 0.05)
    calls: list[int] = []
    agent, _ = make_agent(
        [act("careful_add", a=1, b=2), final("No.")],
        ToolRegistry([async_guarded(calls, delay=5.0)]),
        audit,
    )
    events = await drive(agent, decide=approve)
    observation = next(e for e in events if isinstance(e, Observation))
    assert "could not be checked" in observation.content
    assert calls == [] and not any(isinstance(e, ApprovalRequired) for e in events)
