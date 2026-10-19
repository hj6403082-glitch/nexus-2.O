"""Human in the loop: MUTATING tools wait for an explicit decision."""

import asyncio
from contextlib import aclosing

import pytest

from tests.agent.conftest import ASK, Toolbox, act, drive, final, finished, make_agent
from zeno.agent.audit import MemoryAuditLog
from zeno.agent.events import ApprovalRequired, Observation, ToolCall
from zeno.agent.policy import ApprovalRequest
from zeno.agent.registry import ToolRegistry
from zeno.agent.tools.base import Risk

LIGHT = act("set_light", thought="Turn the kitchen light on.", room="kitchen", on=True)


async def test_mutating_call_pauses_until_approved(
    registry: ToolRegistry, audit: MemoryAuditLog, toolbox: Toolbox
) -> None:
    seen: list[ApprovalRequest] = []

    def approve(request: ApprovalRequest) -> None:
        assert toolbox.calls == []  # nothing has run yet
        seen.append(request)
        assert request.approve() is True

    agent, _ = make_agent([LIGHT, final("Done.")], registry, audit)
    events = await drive(agent, decide=approve)
    kinds = [type(e).__name__ for e in events]
    assert kinds[:4] == ["Thought", "ToolCall", "ApprovalRequired", "Observation"]
    assert toolbox.calls == [("set_light", {"room": "kitchen", "on": True})]
    request = seen[0]
    assert request.tool == "set_light"
    assert request.args == {"room": "kitchen", "on": True}
    assert request.risk is Risk.MUTATING
    assert request.thought == "Turn the kitchen light on."
    assert request.description == "Turn a room's light on or off."
    assert request.id
    assert finished(events).outcome == "answered"


async def test_denied_call_never_runs_and_the_model_is_told(
    registry: ToolRegistry, audit: MemoryAuditLog, toolbox: Toolbox
) -> None:
    agent, engine = make_agent([LIGHT, final("Okay, I left it off.")], registry, audit)
    events = await drive(agent, decide=lambda r: r.deny("not now") and None)
    assert toolbox.calls == []
    observation = next(e for e in events if isinstance(e, Observation))
    assert observation.ok is False
    assert "denied" in observation.content and "not now" in observation.content
    assert "denied" in engine.calls[1][0][-1].content
    assert finished(events).answer == "Okay, I left it off."


async def test_read_only_tools_run_without_approval(
    registry: ToolRegistry, audit: MemoryAuditLog
) -> None:
    agent, _ = make_agent([act("add", a=1, b=2), final("3")], registry, audit)
    events = await drive(agent)
    assert not any(isinstance(e, ApprovalRequired) for e in events)


async def test_no_decision_before_the_deadline_means_no(
    registry: ToolRegistry, audit: MemoryAuditLog, toolbox: Toolbox
) -> None:
    agent, _ = make_agent([LIGHT, final("I'll wait.")], registry, audit, approval_timeout=0.05)
    events = await drive(agent)  # nobody decides
    assert toolbox.calls == []
    observation = next(e for e in events if isinstance(e, Observation))
    assert observation.ok is False and "denied" in observation.content
    approval = [r for r in audit.records if r.kind == "approval"]
    assert approval[0].data["approved"] is False
    assert approval[0].data["by"] == "timeout"


async def test_approval_can_arrive_later_from_another_task(
    registry: ToolRegistry, audit: MemoryAuditLog, toolbox: Toolbox
) -> None:
    def approve_soon(request: ApprovalRequest) -> None:
        asyncio.get_running_loop().call_later(0.02, request.approve)

    agent, _ = make_agent([LIGHT, final("Done.")], registry, audit)
    await drive(agent, decide=approve_soon)
    assert toolbox.calls == [("set_light", {"room": "kitchen", "on": True})]


async def test_abandoning_the_run_at_an_approval_never_runs_the_tool(
    registry: ToolRegistry, audit: MemoryAuditLog, toolbox: Toolbox
) -> None:
    agent, _ = make_agent([LIGHT, final("Done.")], registry, audit)
    async with aclosing(agent.run(ASK)) as events:
        async for event in events:
            if isinstance(event, ApprovalRequired):
                break
    await asyncio.sleep(0)
    assert toolbox.calls == []
    assert audit.records[-1].kind == "run_finished"
    assert audit.records[-1].data["outcome"] == "cancelled"


async def test_a_request_is_decided_once(registry: ToolRegistry, audit: MemoryAuditLog) -> None:
    requests: list[ApprovalRequest] = []

    def decide(request: ApprovalRequest) -> None:
        requests.append(request)
        assert request.decided is False
        assert request.approve(by="boss") is True
        assert request.decided is True
        assert request.approve() is False
        assert request.deny("changed my mind") is False

    agent, _ = make_agent([LIGHT, final("Done.")], registry, audit)
    events = await drive(agent, decide=decide)
    assert any(isinstance(e, Observation) and e.ok for e in events)
    approval = next(r for r in audit.records if r.kind == "approval")
    assert approval.data == {
        "request_id": requests[0].id,
        "approved": True,
        "by": "boss",
        "reason": "",
    }


@pytest.mark.parametrize("approved", [True, False])
async def test_tool_call_is_announced_before_approval(
    registry: ToolRegistry, audit: MemoryAuditLog, approved: bool
) -> None:
    agent, _ = make_agent([LIGHT, final("ok")], registry, audit)
    events = await drive(agent, decide=lambda r: (r.approve() if approved else r.deny()) and None)
    call = next(e for e in events if isinstance(e, ToolCall))
    assert call.risk is Risk.MUTATING
    assert events.index(call) < next(
        i for i, e in enumerate(events) if isinstance(e, ApprovalRequired)
    )
