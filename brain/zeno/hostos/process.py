"""Run one approved program and capture what it says; shared by every OS.

The caller passes the OS-specific parts: how to start the program in its own
process group (``spawn``) and how to stop that whole group (``stop``). stdout and
stderr are read separately and in full, so the program never blocks on a full pipe,
and come back with the exit code so Zeno can read its own errors.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

KILL_GRACE = 1.0
"""Seconds a stopped program gets before the next, harder stop."""


class CommandRefused(ValueError):
    """The command is never run; the message says why."""


Stopper = Callable[[asyncio.subprocess.Process], Awaitable[None]]


def one_line(value: str) -> str:
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError("must be a single line")
    return value


@dataclass(frozen=True, slots=True)
class CommandSettings:
    roots: Sequence[PurePath | str]
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


Runner = Callable[..., Awaitable[RunResult]]


def report(name: str, result: RunResult, timeout: float) -> str:
    """The observation Zeno reads: exit code, then stdout, then stderr."""
    if result.killed:
        head = f"[{name}: killed after {timeout:g} s]"
    else:
        head = f"[{name}: exit {result.exit_code} after {result.elapsed:.1f} s]"
    stdout = result.stdout.rstrip("\n") or "(empty)"
    stderr = result.stderr.rstrip("\n") or "(empty)"
    return f"{head}\n[stdout]\n{stdout}\n[stderr]\n{stderr}"


async def run_process(
    argv: list[str],
    *,
    cwd: str,
    seconds: float,
    env: dict[str, str],
    max_output: int,
    spawn: Mapping[str, Any],
    stop: Stopper,
) -> RunResult:
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **spawn,
    )
    if process.stdout is None or process.stderr is None:  # pipes were asked for above
        raise RuntimeError("the command's output pipes are missing")
    out, err = Capture(max_output), Capture(max_output)
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
        await stop(process)
    finally:
        if process.returncode is None:  # cancelled from outside
            await stop(process)
    # A child that left the group (a daemon) may hold the pipes open; don't wait on it.
    _, pending = await asyncio.wait(readers, timeout=KILL_GRACE)
    for reader in pending:
        reader.cancel()
    elapsed = time.monotonic() - started
    code = None if killed else process.returncode
    return RunResult(code, out.text(), err.text(), elapsed, killed)


class Capture:
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
