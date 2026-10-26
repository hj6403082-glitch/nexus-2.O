"""run_powershell: PowerShell's parser and the policy first, then approval, then a
constrained run whose stdout and stderr go back to Zeno. Everything is faked, so these
run on any OS."""

import base64
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import ValidationError

from tests.agent.conftest import act, drive, final, make_agent
from tests.windows.ps_trees import cmd, dump, one, p, s
from zeno.agent.audit import MemoryAuditLog
from zeno.agent.events import ApprovalRequired, Observation
from zeno.agent.policy import ApprovalRequest
from zeno.agent.registry import ToolRegistry
from zeno.agent.tools.base import Risk, Tool
from zeno.agent.tools.os_windows import PowerShellArgs, powershell_tools
from zeno.hostos.process import CommandRefused, CommandSettings, RunResult
from zeno.hostos.windows import powershell
from zeno.hostos.windows.ps_policy import PsTree, parse_tree

HOME = "C:\\Users\\Boss"
FOLDERS = {HOME.lower(), (HOME + "\\projects").lower(), "c:\\", "c:\\windows"}
LINKS = {(HOME + "\\escape").lower(): "C:\\Windows"}
EXE = "C:\\Program Files\\PowerShell\\7\\pwsh.exe"

TREES = {
    "Get-Process": one(cmd("Get-Process")),
    "Remove-Item C:\\ -Recurse": one(cmd("Remove-Item", s("C:\\"), p("Recurse"))),
    "Get-ChildItem missing": one(cmd("Get-ChildItem", s("missing"))),
}


def realpath(path: str) -> str:
    for link, target in LINKS.items():
        if path.lower() == link or path.lower().startswith(link + "\\"):
            return target + path[len(link) :]
    return path


@dataclass
class FakeParser:
    trees: dict[str, Any] = field(default_factory=lambda: dict(TREES))
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, command: str, *, exe: str, cwd: str, env: dict[str, str]) -> PsTree:
        self.calls.append({"command": command, "exe": exe, "cwd": cwd})
        if command not in self.trees:
            raise CommandRefused("PowerShell's parser could not read it (test)")
        return parse_tree(dump(self.trees[command]))


@dataclass
class FakeRunner:
    result: RunResult = field(default_factory=lambda: RunResult(0, "ok\n", "", 0.2, False))
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(
        self, argv: list[str], *, cwd: str, seconds: float, env: dict[str, str], max_output: int
    ) -> RunResult:
        self.calls.append({"argv": argv, "cwd": cwd, "timeout": seconds, "env": env})
        return self.result


def make(
    runner: FakeRunner | None = None, parser: FakeParser | None = None
) -> tuple[Tool[Any], FakeRunner, FakeParser]:
    fake_runner, fake_parser = runner or FakeRunner(), parser or FakeParser()
    (found,) = powershell_tools(
        CommandSettings(roots=["~"], default_timeout=30, max_output=4000),
        runner=fake_runner,
        parser=fake_parser,
        exe=EXE,
        home=HOME,
        own_pid=4242,
        system_root="C:\\Windows",
        program_dirs=("C:\\Program Files", "C:\\Program Files (x86)"),
        realpath=realpath,
        isdir=lambda path: path.lower() in FOLDERS,
    )
    return found, fake_runner, fake_parser


def approve(request: ApprovalRequest) -> None:
    request.approve()


def args(**values: Any) -> PowerShellArgs:
    return PowerShellArgs.model_validate(values)


async def precheck(tool: Tool[Any], values: PowerShellArgs) -> str | None:
    assert tool.precheck is not None
    result = tool.precheck(values)
    return await result if not isinstance(result, str | None) else result


def test_run_powershell_is_privileged() -> None:
    tool, _, _ = make()
    assert tool.name == "run_powershell" and tool.risk is Risk.PRIVILEGED
    assert "run_powershell" not in ToolRegistry([tool]).for_origin("proactive")


@pytest.mark.parametrize(
    "values",
    [
        {"command": ""},
        {"command": "x" * 1001},
        {"command": "a\nb"},
        {"command": "Get-Process", "timeout": 0},
        {"command": "Get-Process", "timeout": 121},
        {"command": "Get-Process", "shell": True},
    ],
)
def test_arguments_are_bounded(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        args(**values)


async def test_the_precheck_parses_then_applies_the_policy() -> None:
    tool, runner, parser = make()
    assert await precheck(tool, args(command="Get-Process")) is None
    reason = await precheck(tool, args(command="Remove-Item C:\\ -Recurse"))
    assert reason is not None and "protected" in reason
    assert "could not read" in (await precheck(tool, args(command="&&&")) or "")
    assert parser.calls[0] == {"command": "Get-Process", "exe": EXE, "cwd": HOME}
    assert runner.calls == []


async def test_the_working_folder_must_be_inside_the_allowed_roots() -> None:
    tool, _, _ = make()
    assert await precheck(tool, args(command="Get-Process", cwd="projects")) is None
    assert await precheck(tool, args(command="Get-Process", cwd="~\\projects")) is None
    assert (
        await precheck(tool, args(command="Get-Process", cwd=HOME.upper() + "\\PROJECTS")) is None
    )
    for outside in ("C:\\", "C:\\Windows", HOME + "\\..", HOME + "\\missing", "escape"):
        reason = await precheck(tool, args(command="Get-Process", cwd=outside))
        assert reason is not None and "folder" in reason, outside


async def test_runs_constrained_with_a_small_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZENO_API_TOKEN", "secret-token")
    tool, runner, _ = make()
    text = await tool.invoke(args(command="Get-Process", timeout=5))
    call = runner.calls[0]
    argv = call["argv"]
    assert argv[:7] == [
        EXE,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Restricted",
        "-EncodedCommand",
    ]
    script = base64.b64decode(argv[7]).decode("utf-16-le")
    assert script == powershell.PREAMBLE + "Get-Process"
    assert (
        script.splitlines()[-2]
        == "$ExecutionContext.SessionState.LanguageMode = 'ConstrainedLanguage'"
    )
    assert call["cwd"] == HOME and call["timeout"] == 5
    assert "ZENO_API_TOKEN" not in call["env"]
    assert call["env"]["PATH"].split(";")[0] == "C:\\Windows\\System32"
    assert text.startswith("[run_powershell: exit 0 after 0.2 s]")


async def test_stdout_and_stderr_come_back_for_zeno_to_debug() -> None:
    error = "Get-ChildItem : Cannot find path 'C:\\Users\\Boss\\missing'\n"
    tool, _, _ = make(FakeRunner(RunResult(1, "", error, 0.6, False)))
    text = await tool.invoke(args(command="Get-ChildItem missing"))
    assert text == (
        "[run_powershell: exit 1 after 0.6 s]\n[stdout]\n(empty)\n[stderr]\n" + error.rstrip("\n")
    )


async def test_a_timeout_is_reported() -> None:
    tool, _, _ = make(FakeRunner(RunResult(None, "", "", 30.0, True)))
    text = await tool.invoke(args(command="Get-Process"))
    assert text.startswith("[run_powershell: killed after 30 s]")


async def test_the_call_is_checked_again_when_it_runs() -> None:
    tool, runner, _ = make()
    with pytest.raises(ValueError, match="refused"):
        await tool.invoke(args(command="Remove-Item C:\\ -Recurse"))
    assert runner.calls == []


async def test_a_refused_command_never_reaches_the_owner() -> None:
    tool, runner, _ = make()
    asked: list[ApprovalRequest] = []
    agent, _ = make_agent(
        [act("run_powershell", command="Remove-Item C:\\ -Recurse"), final("I won't.")],
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
    tool, _, _ = make(FakeRunner(RunResult(1, "", "boom\n", 0.1, False)))
    agent, _ = make_agent(
        [act("run_powershell", command="Get-Process"), final("It failed.")],
        ToolRegistry([tool]),
        MemoryAuditLog(),
    )
    events = await drive(agent, decide=approve)
    assert any(isinstance(e, ApprovalRequired) for e in events)
    observation = next(e for e in events if isinstance(e, Observation))
    assert observation.ok and "exit 1" in observation.content and "boom" in observation.content


# --- the parser call and the command lines ----------------------------------------------


async def test_parse_command_runs_the_helper_and_reads_its_json() -> None:
    raw = dump(TREES["Get-Process"])
    runner = FakeRunner(RunResult(0, raw, "", 0.3, False))
    tree = await powershell.parse_command("Get-Process", exe=EXE, cwd=HOME, env={}, runner=runner)
    assert tree.root is not None and tree.root.type == "ScriptBlockAst"
    argv = runner.calls[0]["argv"]
    assert argv[:7] == [
        EXE,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
    ]
    assert argv[7].endswith("ps_parse.ps1")
    assert base64.b64decode(argv[8]).decode("utf-8") == "Get-Process"


@pytest.mark.parametrize(
    "result", [RunResult(1, "", "boom", 0.1, False), RunResult(None, "", "", 12.0, True)]
)
async def test_a_failed_parse_refuses(result: RunResult) -> None:
    with pytest.raises(CommandRefused, match="parser"):
        await powershell.parse_command("x", exe=EXE, cwd=HOME, env={}, runner=FakeRunner(result))


def test_powershell_7_is_preferred_when_installed() -> None:
    programs = ("C:\\Program Files", "C:\\Program Files (x86)")
    found = powershell.find_powershell("C:\\Windows", programs, exists=lambda path: path == EXE)
    assert found == EXE
    fallback = powershell.find_powershell("C:\\Windows", programs, exists=lambda path: False)
    assert fallback == "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"


async def test_a_failed_parse_says_why_in_plain_text() -> None:
    # PowerShell 7 colours its errors and spreads them over several lines.
    stderr = (
        "\x1b[31;1mJoin-Path: \x1b[0mThe term 'Join-Path' is not recognized.\n"
        "\x1b[36;1m     | \x1b[31;1mCheck the spelling of the name.\x1b[0m\n\n"
    )
    runner = FakeRunner(RunResult(1, "", stderr, 0.1, False))
    with pytest.raises(CommandRefused) as refused:
        await powershell.parse_command("x", exe=EXE, cwd=HOME, env={}, runner=runner)
    message = str(refused.value)
    assert "\x1b" not in message
    assert "The term 'Join-Path' is not recognized" in message
