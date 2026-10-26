"""Start and stop a Windows command: its own process group, no console window, and on a
timeout the whole process tree is killed (Windows has no process groups to signal)."""

import asyncio
import contextlib
import sys
from typing import Any

import psutil

from zeno.hostos.process import KILL_GRACE, RunResult, run_process

CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def spawn_options() -> dict[str, Any]:
    if sys.platform == "win32":
        return {"creationflags": CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW}
    return {"start_new_session": True}  # PowerShell 7 on Linux runs these tests in CI


async def stop_tree(process: asyncio.subprocess.Process, *, ps: Any = psutil) -> None:
    """Kill the process and everything it started, children first."""
    victims = []
    with contextlib.suppress(ps.NoSuchProcess, ps.AccessDenied):
        root = ps.Process(process.pid)
        victims = [*root.children(recursive=True), root]
    for victim in victims:
        with contextlib.suppress(ps.NoSuchProcess, ps.AccessDenied):
            victim.kill()
    if not victims:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(KILL_GRACE):
            await process.wait()


async def run_windows_process(
    argv: list[str], *, cwd: str, seconds: float, env: dict[str, str], max_output: int
) -> RunResult:
    return await run_process(
        argv,
        cwd=cwd,
        seconds=seconds,
        env=env,
        max_output=max_output,
        spawn=spawn_options(),
        stop=stop_tree,
    )
