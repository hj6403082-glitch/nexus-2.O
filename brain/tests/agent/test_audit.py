"""Append-only, structured audit trail of everything the agent does."""

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from tests.agent.conftest import Toolbox, act, drive, final, make_agent
from zeno.agent.audit import AuditError, AuditRecord, JsonlAuditLog, MemoryAuditLog, read_audit
from zeno.agent.registry import ToolRegistry


async def test_a_tool_run_is_fully_recorded(registry: ToolRegistry, audit: MemoryAuditLog) -> None:
    agent, _ = make_agent([act("add", thought="Add.", a=2, b=3), final("5")], registry, audit)
    await drive(agent)
    assert [(r.kind, r.step) for r in audit.records] == [
        ("run_started", 0),
        ("thought", 1),
        ("action", 1),
        ("observation", 1),
        ("thought", 2),
        ("final", 2),
        ("run_finished", 2),
    ]
    by_kind = {r.kind: r.data for r in audit.records}
    assert by_kind["run_started"]["input"] == "What is 2 + 3?"
    assert by_kind["thought"]["text"] == "I know the answer."
    assert by_kind["action"] == {"tool": "add", "args": {"a": 2, "b": 3}, "risk": "read_only"}
    assert by_kind["observation"] == {"tool": "add", "ok": True, "content": "5"}
    assert by_kind["final"] == {"answer": "5"}
    assert by_kind["run_finished"] == {"outcome": "answered", "steps": 2}
    assert len({r.run_id for r in audit.records}) == 1
    timestamps = [r.ts for r in audit.records]
    assert timestamps == sorted(timestamps)


async def test_approvals_and_denials_are_recorded(
    registry: ToolRegistry, audit: MemoryAuditLog
) -> None:
    light = act("set_light", room="hall", on=False)
    agent, _ = make_agent([light, final("ok")], registry, audit)
    await drive(agent, decide=lambda r: r.deny("too late", by="boss") and None)
    kinds = [r.kind for r in audit.records]
    assert kinds[2:6] == ["action", "approval_requested", "approval", "observation"]
    requested = audit.records[3].data
    assert requested["tool"] == "set_light"
    assert requested["args"] == {"room": "hall", "on": False}
    decision = audit.records[4].data
    assert decision == {
        "request_id": requested["request_id"],
        "approved": False,
        "by": "boss",
        "reason": "too late",
    }


async def test_failures_and_breakers_are_recorded(
    registry: ToolRegistry, audit: MemoryAuditLog
) -> None:
    script = [
        "garbage",
        act("explode", a=1, b=1),
        act("slow", seconds=5),
        act("add", a=1, b=1),
        act("add", a=1, b=1),
        act("add", a=1, b=1),
    ]
    agent, _ = make_agent(script, registry, audit, max_steps=6)
    await drive(agent)
    rejected = next(r for r in audit.records if r.kind == "step_rejected")
    assert rejected.data["raw"] == "garbage"
    failures = [r.data for r in audit.records if r.kind == "observation" and not r.data["ok"]]
    assert "RuntimeError" in failures[0]["content"]
    assert "timed out" in failures[1]["content"]
    aborted = next(r for r in audit.records if r.kind == "aborted")
    assert aborted.data["reason"] == "loop_detected"
    assert aborted.data["tool"] == "add"
    assert audit.records[-1].data["outcome"] == "loop_detected"


async def test_each_run_has_its_own_id(registry: ToolRegistry, audit: MemoryAuditLog) -> None:
    agent, _ = make_agent([final("a"), final("b")], registry, audit)
    await drive(agent)
    await drive(agent)
    assert len({r.run_id for r in audit.records}) == 2


async def test_jsonl_log_writes_one_json_object_per_line(tmp_path: Path) -> None:
    path = tmp_path / "audit" / "agent.jsonl"
    log = JsonlAuditLog(path)
    await log.record(
        AuditRecord(ts=1.0, run_id="r1", step=0, kind="run_started", data={"input": "hi"})
    )
    await log.record(AuditRecord(ts=2.0, run_id="r1", step=1, kind="final", data={"answer": "ok"}))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["kind"] for line in lines] == ["run_started", "final"]
    assert json.loads(lines[0]) == {
        "ts": 1.0,
        "run_id": "r1",
        "step": 0,
        "kind": "run_started",
        "data": {"input": "hi"},
    }


async def test_jsonl_log_only_ever_appends(tmp_path: Path) -> None:
    path = tmp_path / "agent.jsonl"
    path.write_text('{"earlier": "entry"}\n', encoding="utf-8")
    await JsonlAuditLog(path).record(AuditRecord(1.0, "r1", 0, "run_started", {}))
    await JsonlAuditLog(path).record(AuditRecord(2.0, "r2", 0, "run_started", {}))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == '{"earlier": "entry"}'
    assert len(lines) == 3


def test_jsonl_log_has_no_way_to_rewrite_history() -> None:
    public = {name for name in dir(JsonlAuditLog) if not name.startswith("_")}
    assert public == {"record", "path"}


async def test_full_run_round_trips_through_the_file(
    registry: ToolRegistry, tmp_path: Path, toolbox: Toolbox
) -> None:
    path = tmp_path / "agent.jsonl"
    from zeno.agent.loop import ReActAgent
    from zeno.inference.fake import ScriptedEngine

    agent = ReActAgent(
        ScriptedEngine([act("add", a=2, b=3), final("5")]), registry, audit=JsonlAuditLog(path)
    )
    await drive(agent)
    records = read_audit(path)
    assert [r.kind for r in records][-1] == "run_finished"
    assert records[2].data == {"tool": "add", "args": {"a": 2, "b": 3}, "risk": "read_only"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
async def test_jsonl_log_is_private_to_the_owner(tmp_path: Path) -> None:
    path = tmp_path / "agent.jsonl"
    await JsonlAuditLog(path).record(AuditRecord(1.0, "r", 0, "run_started", {}))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


class BrokenLog:
    def __init__(self, fail_on: str) -> None:
        self.fail_on = fail_on

    async def record(self, record: AuditRecord) -> None:
        if record.kind == self.fail_on:
            raise AuditError("disk full")


async def test_no_tool_runs_if_its_action_cannot_be_audited(
    registry: ToolRegistry, toolbox: Toolbox
) -> None:
    # Fail closed: an unrecorded action must not happen.
    from zeno.agent.loop import ReActAgent
    from zeno.inference.fake import ScriptedEngine

    agent = ReActAgent(
        ScriptedEngine([act("add", a=1, b=2), final("3")]), registry, audit=BrokenLog("action")
    )
    with pytest.raises(AuditError):
        await drive(agent)
    assert toolbox.calls == []


async def test_unwritable_log_raises_audit_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    log = JsonlAuditLog(blocker / "agent.jsonl")  # parent is a file
    with pytest.raises(AuditError):
        await log.record(AuditRecord(1.0, "r", 0, "run_started", {}))
