"""The PRIVILEGED tier: always approved by the owner, never offered to proactive runs."""

from tests.agent.conftest import AddArgs, Toolbox, act, drive, final, finished, make_agent
from zeno.agent.audit import MemoryAuditLog
from zeno.agent.events import ApprovalRequired
from zeno.agent.policy import ApprovalRequest, available_in, needs_approval
from zeno.agent.registry import ToolRegistry
from zeno.agent.tools.base import Risk, Tool, tool


def remote_tool(calls: list[int]) -> Tool[AddArgs]:
    @tool(risk=Risk.PRIVILEGED, timeout=1.0)
    async def remote_add(args: AddArgs) -> str:
        """Add two integers on another machine."""
        calls.append(args.a + args.b)
        return str(args.a + args.b)

    return remote_add


def test_every_risk_but_read_only_needs_approval() -> None:
    assert not needs_approval(Risk.READ_ONLY)
    assert needs_approval(Risk.MUTATING)
    assert needs_approval(Risk.PRIVILEGED)


def test_privileged_tools_are_only_available_to_the_owner_in_chat() -> None:
    assert all(available_in(risk, "chat") for risk in Risk)
    assert available_in(Risk.READ_ONLY, "proactive")
    assert available_in(Risk.MUTATING, "proactive")
    assert not available_in(Risk.PRIVILEGED, "proactive")


def test_a_proactive_registry_cannot_even_name_a_privileged_tool(toolbox: Toolbox) -> None:
    registry = ToolRegistry([*toolbox.all(), remote_tool([])])
    proactive = registry.for_origin("proactive")
    assert "remote_add" not in proactive
    assert proactive.names() == ["add", "set_light", "slow", "explode"]
    assert "remote_add" not in proactive.instructions()
    assert registry.for_origin("chat").names() == registry.names()


def test_instructions_say_a_privileged_tool_needs_approval(toolbox: Toolbox) -> None:
    text = ToolRegistry([toolbox.add, remote_tool([])]).instructions()
    line = next(line for line in text.splitlines() if line.startswith("- remote_add"))
    assert "approval" in line and "privileged" in line


async def test_a_privileged_call_waits_for_the_owner(audit: MemoryAuditLog) -> None:
    calls: list[int] = []
    registry = ToolRegistry([remote_tool(calls)])
    seen: list[ApprovalRequest] = []

    def deny(request: ApprovalRequest) -> None:
        seen.append(request)
        request.deny("Not now.")

    agent, _ = make_agent([act("remote_add", a=2, b=3), final("Okay.")], registry, audit)
    events = await drive(agent, decide=deny)
    assert any(isinstance(e, ApprovalRequired) for e in events)
    assert seen[0].risk is Risk.PRIVILEGED
    assert calls == []
    assert finished(events).outcome == "answered"
