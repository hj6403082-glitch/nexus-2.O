"""Facts about the machine Zeno runs on (read from Python, no subprocesses)."""

import os
import platform

from zeno.agent.tools.base import Risk, ToolArgs, tool


class SystemArgs(ToolArgs):
    pass


@tool(risk=Risk.READ_ONLY, timeout=2.0)
async def get_system_info(args: SystemArgs) -> str:
    """Describe this computer: operating system, architecture, CPUs and Python version."""
    return (
        f"{platform.system()} {platform.release()} ({platform.machine()}), "
        f"{os.cpu_count() or 'unknown'} CPUs, Python {platform.python_version()}"
    )
