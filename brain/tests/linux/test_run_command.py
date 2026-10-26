"""run_command: one checked command, no shell, stdout and stderr fed back to Zeno."""

import os
import posixpath
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tests.agent.conftest import act, drive, final, make_agent
from zeno.agent.audit import MemoryAuditLog
from zeno.agent.events import ApprovalRequired, Observation
from zeno.agent.policy import ApprovalRequest
from zeno.agent.registry import ToolRegistry
from zeno.agent.tools.base import Risk, Tool
from zeno.agent.tools.os_linux import CommandArgs, CommandSettings, command_tools
from zeno.hostos.process import RunResult

# The tool's tests use a pretend Linux file system, so they run on any OS. Only the
# tests of the real runner, at the end, need Linux.
HOME = "/home/boss"
FOLDERS = {HOME, f"{HOME}/project", "/", "/etc"}
LINKS = {f"{HOME}/escape": "/etc"}
linux_only = pytest.mark.skipif(sys.platform != "linux", reason="runs real Linux programs")


def fake_realpath(path: str) -> str:
    path = posixpath.normpath(path)
    for link, target in LINKS.items():
        if path == link or path.startswith(link + "/"):
            return target + path[len(link) :]
    return path


@dataclass
class FakeRunner:
    result: RunResult = field(default_factory=lambda: RunResult(0, "ok\n", "", 0.1, False))
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(
        self, argv: list[str], *, cwd: str, seconds: float, env: dict[str, str], max_output: int
    ) -> RunResult:
        self.calls.append(
            {"argv": argv, "cwd": cwd, "timeout": seconds, "env": env, "max_output": max_output}
        )
        return self.result


def which(name: str) -> str | None:
    return None if name == "missing" else f"/usr/bin/{name}"


def run_command(runner: Any = None, **settings: Any) -> tuple[Tool[Any], FakeRunner]:
    fake = runner or FakeRunner()
    config = CommandSettings(roots=["~"], default_timeout=30, max_output=4000, **settings)
    (found,) = command_tools(
        config,
        runner=fake,
        which=which,
        home=HOME,
        realpath=fake_realpath,
        isdir=FOLDERS.__contains__,
    )
    return found, fake


def args(**values: Any) -> CommandArgs:
    return CommandArgs.model_validate(values)


def test_run_command_is_privileged() -> None:
    tool, _ = run_command()
    assert tool.name == "run_command" and tool.risk is Risk.PRIVILEGED
    assert tool.precheck is not None


@pytest.mark.parametrize(
    "values",
    [
        {"command": ""},
        {"command": "x" * 1001},
        {"command": "ls", "timeout": 0},
        {"command": "ls", "timeout": 121},
        {"command": "ls", "shell": True},
    ],
)
def test_arguments_are_bounded(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        args(**values)


def test_the_precheck_refuses_dangerous_commands() -> None:
    tool, _ = run_command()
    assert tool.precheck is not None
    assert "refused" in (tool.precheck(args(command="rm -rf /")) or "")
    assert "no shell" in (tool.precheck(args(command="ls | wc")) or "")
    assert tool.precheck(args(command="ls -la")) is None


def test_the_working_folder_must_be_inside_the_allowed_roots() -> None:
    tool, _ = run_command()
    assert tool.precheck is not None
    assert tool.precheck(args(command="ls", cwd=f"{HOME}/project")) is None
    assert tool.precheck(args(command="ls", cwd="project")) is None  # relative to home
    assert tool.precheck(args(command="ls", cwd="~/project")) is None
    for outside in ("/", "/etc", f"{HOME}/..", f"{HOME}/missing", "/home/boss2"):
        reason = tool.precheck(args(command="ls", cwd=outside))
        assert reason is not None and "folder" in reason


def test_a_symlink_out_of_the_roots_is_refused() -> None:
    tool, _ = run_command()
    assert tool.precheck is not None
    assert tool.precheck(args(command="ls", cwd="escape")) is not None


async def test_runs_the_checked_argv_with_a_small_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZENO_API_TOKEN", "secret-token")
    tool, runner = run_command()
    text = await tool.invoke(args(command="ls -la ~", timeout=5))
    call = runner.calls[0]
    assert call["argv"] == ["/usr/bin/ls", "-la", HOME]
    assert call["cwd"] == HOME and call["timeout"] == 5
    assert "ZENO_API_TOKEN" not in call["env"]
    assert call["env"]["PATH"].split(":")[0] == "/usr/bin"
    assert call["env"]["TERM"] == "dumb"
    assert text.startswith("[run_command: exit 0 after 0.1 s]")


async def test_stdout_and_stderr_come_back_separately() -> None:
    runner = FakeRunner(RunResult(2, "partial\n", "ls: cannot access 'x'\n", 0.4, False))
    tool, _ = run_command(runner)
    text = await tool.invoke(args(command="ls x"))
    assert text == (
        "[run_command: exit 2 after 0.4 s]\n[stdout]\npartial\n[stderr]\nls: cannot access 'x'"
    )


async def test_a_timeout_is_reported() -> None:
    tool, _ = run_command(FakeRunner(RunResult(None, "", "", 30.0, True)))
    text = await tool.invoke(args(command="sleep 100"))
    assert text.startswith("[run_command: killed after 30 s]")
    assert "[stdout]\n(empty)" in text


async def test_the_call_is_checked_again_when_it_runs() -> None:
    tool, runner = run_command()
    with pytest.raises(ValueError, match="refused"):
        await tool.invoke(args(command="rm -rf /"))
    assert runner.calls == []


# --- through the agent loop ---------------------------------------------------------


async def test_a_refused_command_never_reaches_the_owner() -> None:
    tool, runner = run_command()
    asked: list[ApprovalRequest] = []
    agent, _ = make_agent(
        [act("run_command", command="rm -rf /"), final("I won't.")],
        ToolRegistry([tool]),
        MemoryAuditLog(),
    )

    def decide(request: ApprovalRequest) -> None:
        asked.append(request)
        request.approve()

    events = await drive(agent, decide=decide)
    assert asked == [] and runner.calls == []
    observation = next(e for e in events if isinstance(e, Observation))
    assert "Refused before asking the owner" in observation.content


async def test_an_allowed_command_waits_for_approval_and_errors_come_back() -> None:
    tool, _ = run_command(FakeRunner(RunResult(1, "", "boom\n", 0.1, False)))
    agent, _ = make_agent(
        [act("run_command", command="false"), final("It failed.")],
        ToolRegistry([tool]),
        MemoryAuditLog(),
    )

    def approve(request: ApprovalRequest) -> None:
        request.approve()

    events = await drive(agent, decide=approve)
    assert any(isinstance(e, ApprovalRequired) for e in events)
    observation = next(e for e in events if isinstance(e, Observation))
    assert observation.ok and "exit 1" in observation.content and "boom" in observation.content


def test_proactive_runs_never_see_run_command() -> None:
    tool, _ = run_command()
    assert "run_command" not in ToolRegistry([tool]).for_origin("proactive")


# --- the real runner (harmless programs only) ---------------------------------------


def real_tool(tmp_path: Path, **settings: Any) -> Tool[Any]:
    config = CommandSettings(roots=[tmp_path], default_timeout=30, max_output=200, **settings)
    (found,) = command_tools(config, home=str(tmp_path))
    return found


@linux_only
@pytest.mark.skipif(shutil.which("printf") is None, reason="needs printf")
async def test_the_real_runner_captures_both_streams(tmp_path: Path) -> None:
    tool = real_tool(tmp_path)
    text = await tool.invoke(args(command="printf 'hello\\nworld'"))
    assert "exit 0" in text and "hello\nworld" in text
    text = await tool.invoke(args(command="ls /definitely-not-here"))
    assert "exit 2" in text and "[stderr]" in text and "definitely-not-here" in text


@linux_only
async def test_the_real_runner_caps_output(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_bytes(b"y\n" * 10_000)
    text = await real_tool(tmp_path).invoke(args(command="cat big.txt", cwd=str(tmp_path)))
    stdout = text.split("[stdout]\n")[1].split("\n[stderr]")[0]
    assert len(stdout) < 300 and "cut" in stdout


@linux_only
async def test_the_real_runner_kills_the_whole_group_on_timeout(tmp_path: Path) -> None:
    text = await real_tool(tmp_path).invoke(args(command="sleep 30", timeout=1))
    assert text.startswith("[run_command: killed after 1 s]")


@linux_only
async def test_the_real_runner_gets_no_brain_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZENO_API_TOKEN", "secret-token")
    text = await real_tool(
        tmp_path,
    ).invoke(args(command="printenv"))
    assert "secret-token" not in text and os.environ["PATH"] != ""


@linux_only
async def test_a_child_holding_the_pipes_does_not_hang_the_tool(tmp_path: Path) -> None:
    from zeno.hostos.linux.process import run_linux_process

    sleeper = shutil.which("sleep")
    setsid = shutil.which("setsid")
    if sleeper is None or setsid is None:
        pytest.skip("needs sleep and setsid")
    # The policy refuses setsid; the runner itself must still cope with such a child.
    result = await run_linux_process(
        [setsid, "-f", sleeper, "20"], cwd=str(tmp_path), seconds=5, env={}, max_output=100
    )
    assert result.exit_code == 0 and result.elapsed < 4
