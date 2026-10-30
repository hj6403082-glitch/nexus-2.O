"""Start and stop a Linux command as its own process group."""

import asyncio
import contextlib
import os
import signal
import sys

from zeno.hostos.process import KILL_GRACE, RunResult, run_process


async def stop_group(process: asyncio.subprocess.Process) -> None:
    """SIGTERM the whole group, then SIGKILL it if it hasn't gone."""
    if sys.platform == "win32":  # imported on Windows only by tests, never run there
        raise RuntimeError("process groups are a Unix feature")
    for sig in (signal.SIGTERM, signal.SIGKILL):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, sig)
        try:
            async with asyncio.timeout(KILL_GRACE):
                await process.wait()
            return
        except TimeoutError:
            continue


async def run_linux_process(
    argv: list[str], *, cwd: str, seconds: float, env: dict[str, str], max_output: int
) -> RunResult:
    return await run_process(
        argv,
        cwd=cwd,
        seconds=seconds,
        env=env,
        max_output=max_output,
        spawn={"start_new_session": True},  # its own group, so a timeout stops all of it
        stop=stop_group,
    )
