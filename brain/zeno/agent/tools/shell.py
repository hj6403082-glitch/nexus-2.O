"""run_command: run one checked command on this machine, with the owner's approval.

There is no shell. The command line is split into an argument list by the command
policy, which refuses dangerous commands before the owner is even asked (the tool's
``precheck``). An approved command starts with ``create_subprocess_exec`` in its own
process group, with stdin closed, a small environment and a time limit. stdout and
stderr come back separately with the exit code, so Zeno can read its own errors.
"""

import asyncio
import contextlib
import os
import shutil
import signal
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import AfterValidator, Field

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool
from zeno.agent.tools.command_policy import (
    TRUSTED_DIRS,
    CommandRefused,
    PolicyContext,
    check_command,
)

# What a command gets from Zeno's environment: enough for systemctl --user and
# locale-aware tools, none of the brain's own settings or secrets.
_ENV_KEYS = (
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
)
_KILL_GRACE = 1.0


def _one_line(value: str) -> str:
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError("must be a single line")
    return value


class CommandArgs(ToolArgs):
    command: Annotated[str, Field(min_length=1, max_length=1000), AfterValidator(_one_line)]
    cwd: str | None = Field(
        None, max_length=500, description="Working folder; defaults to the home folder."
    )
    timeout: int | None = Field(None, ge=1, le=120, description="Seconds before it is stopped.")


@dataclass(frozen=True, slots=True)
class CommandSettings:
    roots: Sequence[Path]
    """Folders the working folder must be inside."""
    default_timeout: float = 30.0
    max_output: int = 4000


@dataclass(frozen=True, slots=True)
class RunResult:
    exit_code: int | None
    stdout: str
    stderr: str
    elapsed: float
    killed: bool


def trusted_which(name: str) -> str | None:
    """Find a program in the trusted system folders only; PATH is ignored."""
    return shutil.which(name, path=os.pathsep.join(TRUSTED_DIRS))


def shell_tools(
    settings: CommandSettings,
    *,
    runner: Callable[..., Awaitable[RunResult]] | None = None,
    which: Callable[[str], str | None] = trusted_which,
    home: str | None = None,
) -> list[Tool[Any]]:
    run = runner or run_process
    home_dir = home or str(Path.home())
    roots = [Path(os.path.realpath(root.expanduser())) for root in settings.roots]

    def plan(args: CommandArgs) -> tuple[list[str], str]:
        """The checked argv and working folder, or ``CommandRefused``."""
        folder = Path(os.path.expanduser(args.cwd or home_dir))
        if not folder.is_absolute():
            folder = Path(home_dir) / folder
        real = Path(os.path.realpath(folder))
        if not real.is_dir() or not any(real == r or r in real.parents for r in roots):
            raise CommandRefused(
                f"the working folder {args.cwd or home_dir} is not an existing folder inside "
                f"{', '.join(str(r) for r in roots)}"
            )
        context = PolicyContext(
            home=home_dir,
            cwd=str(real),
            own_pid=os.getpid(),
            which=which,
            realpath=os.path.realpath,
        )
        return check_command(args.command, context), str(real)

    def precheck(args: CommandArgs) -> str | None:
        try:
            plan(args)
        except CommandRefused as refusal:
            return str(refusal)
        return None

    # Outlasts the longest allowed command, so the runner's own timeout is reported.
    @tool(risk=Risk.PRIVILEGED, timeout=120 + _KILL_GRACE + 5.0, precheck=precheck)
    async def run_command(args: CommandArgs) -> str:
        """Run one program on this computer (no shell: no pipes, redirects or wildcards)
        and return its exit code, stdout and stderr. Needs the owner's approval."""
        try:
            argv, cwd = plan(args)  # checked again: the folder may have changed since
        except CommandRefused as refusal:
            raise ValueError(f"refused: {refusal}") from refusal
        timeout = float(args.timeout or settings.default_timeout)
        result = await run(
            argv, cwd=cwd, seconds=timeout, env=_environment(), max_output=settings.max_output
        )
        return _report(result, timeout)

    return [run_command]


def _environment() -> dict[str, str]:
    env = {key: os.environ[key] for key in _ENV_KEYS if key in os.environ}
    env["PATH"] = os.pathsep.join(TRUSTED_DIRS)
    env["TERM"] = "dumb"
    return env


def _report(result: RunResult, timeout: float) -> str:
    if result.killed:
        head = f"[run_command: killed after {timeout:g} s]"
    else:
        head = f"[run_command: exit {result.exit_code} after {result.elapsed:.1f} s]"
    stdout = result.stdout.rstrip("\n") or "(empty)"
    stderr = result.stderr.rstrip("\n") or "(empty)"
    return f"{head}\n[stdout]\n{stdout}\n[stderr]\n{stderr}"


async def run_process(
    argv: list[str], *, cwd: str, seconds: float, env: dict[str, str], max_output: int
) -> RunResult:
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,  # its own process group, so a timeout stops all of it
    )
    if process.stdout is None or process.stderr is None:  # pipes were asked for above
        raise RuntimeError("the command's output pipes are missing")
    out, err = _Capture(max_output), _Capture(max_output)
    readers = {
        asyncio.ensure_future(out.read(process.stdout)),
        asyncio.ensure_future(err.read(process.stderr)),
    }
    killed = False
    try:
        async with asyncio.timeout(seconds):
            await process.wait()
    except TimeoutError:
        killed = True
        await _stop_group(process)
    finally:
        if process.returncode is None:  # cancelled from outside
            await _stop_group(process)
    # A child that left the group (a daemon) may hold the pipes open; don't wait on it.
    _, pending = await asyncio.wait(readers, timeout=_KILL_GRACE)
    for reader in pending:
        reader.cancel()
    elapsed = time.monotonic() - started
    code = None if killed else process.returncode
    return RunResult(code, out.text(), err.text(), elapsed, killed)


async def _stop_group(process: asyncio.subprocess.Process) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, sig)
        try:
            async with asyncio.timeout(_KILL_GRACE):
                await process.wait()
            return
        except TimeoutError:
            continue


class _Capture:
    """Reads a whole stream (so the program never blocks on a full pipe), keeps the start."""

    def __init__(self, cap: int) -> None:
        self._cap = cap
        self._kept = bytearray()
        self._total = 0

    async def read(self, stream: asyncio.StreamReader) -> None:
        limit = self._cap * 4  # bytes; decoded and cut to characters in text()
        while chunk := await stream.read(65536):
            self._total += len(chunk)
            if len(self._kept) < limit:
                self._kept += chunk[: limit - len(self._kept)]

    def text(self) -> str:
        text = self._kept.decode("utf-8", errors="replace")
        if len(text) > self._cap or self._total > len(self._kept):
            text = text[: self._cap] + f"\n[... output cut at {self._cap} characters]"
        return text
