"""Zeno's Windows toolset: run_powershell, notify_desktop (toasts) and service_status.

run_powershell never hands raw text to PowerShell unchecked. PowerShell's own parser
reads the command first (``ps_parse.ps1`` parses, never runs), and the pure policy in
``ps_policy`` refuses anything outside a small static subset of the language before
the owner is even asked (the tool's ``precheck``). An approved command runs with no
profile, no script files (``-ExecutionPolicy Restricted``) and in Constrained Language
Mode, with stdin closed, a small environment and a time limit. stdout and stderr come
back separately with the exit code, so Zeno can read its own errors.

Nothing here imports Linux code; ``os_loader`` loads this module on Windows only.
"""

import asyncio
import ntpath
import os
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any, Literal

import psutil
from pydantic import AfterValidator, Field, StringConstraints

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool
from zeno.agent.tools.os_loader import OsToolset
from zeno.agent.tools.telemetry import telemetry_tools
from zeno.config import Settings
from zeno.hostos.desktop import Notifier, notify_tool
from zeno.hostos.process import (
    KILL_GRACE,
    CommandRefused,
    CommandSettings,
    Runner,
    one_line,
    report,
)
from zeno.hostos.windows import powershell
from zeno.hostos.windows.process import run_windows_process
from zeno.hostos.windows.ps_policy import PsContext, PsTree, check_powershell

__all__ = [
    "PowerShellArgs",
    "ServiceArgs",
    "desktop_tools",
    "powershell_tools",
    "windows_tools",
]

# What a command gets from Zeno's environment: what Windows programs need to work,
# none of the brain's own settings or secrets.
_ENV_KEYS = (
    "SYSTEMROOT",
    "WINDIR",
    "SYSTEMDRIVE",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "USERNAME",
    "USERDOMAIN",
    "COMPUTERNAME",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "COMMONPROGRAMFILES",
    "TEMP",
    "TMP",
    "PATHEXT",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
)

Parser = Callable[..., Awaitable[PsTree]]


class PowerShellArgs(ToolArgs):
    command: Annotated[str, Field(min_length=1, max_length=1000), AfterValidator(one_line)]
    cwd: str | None = Field(
        None, max_length=500, description="Working folder; defaults to the profile folder."
    )
    timeout: int | None = Field(None, ge=1, le=120, description="Seconds before it is stopped.")


class ServiceArgs(ToolArgs):
    name: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.$@-]{1,80}$")] = Field(
        description="A service name such as Spooler or wuauserv."
    )
    scope: Literal["system", "user"] = "system"
    """Kept so the tool reads the same on every OS; Windows services are machine-wide."""


def windows_tools(
    settings: Settings, command: CommandSettings, *, notifier: Notifier | None = None
) -> OsToolset:
    """What ``os_loader`` registers on Windows, as the owner's settings turn it on."""
    toolset = OsToolset()
    if settings.os_tools:
        if notifier is None:
            from zeno.hostos.windows.toast import WindowsToaster  # WinRT loads on first toast

            notifier = WindowsToaster()
        toolset.tools += telemetry_tools()
        toolset.tools += desktop_tools(notifier, per_hour=settings.desktop_notify_per_hour)
    if settings.run_command:
        toolset.tools += powershell_tools(command)
    return toolset


def _system_root() -> str:
    return os.environ.get("SYSTEMROOT", "C:\\Windows")


def _program_dirs() -> tuple[str, ...]:
    return (
        os.environ.get("PROGRAMFILES", "C:\\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
    )


def _native_realpath(path: str) -> str:
    return os.path.realpath(path) if sys.platform == "win32" else path


def powershell_tools(
    settings: CommandSettings,
    *,
    runner: Runner | None = None,
    parser: Parser | None = None,
    exe: str | None = None,
    home: str | None = None,
    own_pid: int | None = None,
    system_root: str | None = None,
    program_dirs: tuple[str, ...] | None = None,
    realpath: Callable[[str], str] = _native_realpath,
    isdir: Callable[[str], bool] = os.path.isdir,
) -> list[Tool[Any]]:
    """run_powershell. Paths are Windows strings throughout, and the file system calls
    are passed in, so the tool's tests run on any OS."""
    run = runner or run_windows_process
    parse = parser or powershell.parse_command
    home_dir = home or str(Path.home())
    root_dir = system_root or _system_root()
    programs = program_dirs or _program_dirs()
    program = exe or powershell.find_powershell(root_dir, programs, exists=os.path.isfile)
    pid = own_pid if own_pid is not None else os.getpid()
    roots = [realpath(_absolute(str(root), home_dir)) for root in settings.roots]
    env = _environment(root_dir, program)

    async def plan(args: PowerShellArgs) -> str:
        """The checked working folder, or ``CommandRefused``."""
        folder = realpath(_absolute(args.cwd or home_dir, home_dir))
        if not isdir(folder) or not any(_within(folder, root) for root in roots):
            raise CommandRefused(
                f"the working folder {args.cwd or home_dir} is not an existing folder inside "
                f"{', '.join(roots)}"
            )
        tree = await parse(args.command, exe=program, cwd=folder, env=env)
        context = PsContext(
            home=home_dir,
            cwd=folder,
            own_pid=pid,
            system_root=root_dir,
            program_dirs=programs,
            realpath=realpath,
        )
        check_powershell(tree, context)
        return folder

    async def precheck(args: PowerShellArgs) -> str | None:
        try:
            await plan(args)
        except CommandRefused as refusal:
            return str(refusal)
        return None

    # Outlasts the longest command plus its parse, so the runner's own timeout is reported.
    timeout = 120 + powershell.PARSE_SECONDS + KILL_GRACE + 5.0

    @tool(risk=Risk.PRIVILEGED, timeout=timeout, precheck=precheck)
    async def run_powershell(args: PowerShellArgs) -> str:
        """Run one PowerShell command on this computer (one pipeline; no scripts, no ;)
        and return its exit code, stdout and stderr. Needs the owner's approval."""
        try:
            cwd = await plan(args)  # checked again: the folder may have changed since
        except CommandRefused as refusal:
            raise ValueError(f"refused: {refusal}") from refusal
        seconds = float(args.timeout or settings.default_timeout)
        result = await run(
            powershell.run_argv(program, args.command),
            cwd=cwd,
            seconds=seconds,
            env=env,
            max_output=settings.max_output,
        )
        return report("run_powershell", result, seconds)

    return [run_powershell]


def _absolute(path: str, home: str) -> str:
    if path == "~" or path.startswith(("~\\", "~/")):
        path = home + path[1:]
    return ntpath.normpath(ntpath.join(home, path))  # an absolute path wins the join


def _within(path: str, root: str) -> bool:
    path, root = path.lower(), root.lower()
    return path == root or path.startswith(root.rstrip("\\") + "\\")


def _environment(system_root: str, program: str) -> dict[str, str]:
    env = {key: os.environ[key] for key in _ENV_KEYS if key in os.environ}
    system32 = ntpath.join(system_root, "System32")
    folders = [
        system32,
        system_root,
        ntpath.join(system32, "Wbem"),
        ntpath.join(system32, "WindowsPowerShell", "v1.0"),
        ntpath.join(system32, "OpenSSH"),
    ]
    if ntpath.dirname(program) not in folders:
        folders.append(ntpath.dirname(program))
    env["PATH"] = ";".join(folders)
    env["PSModulePath"] = ntpath.join(system32, "WindowsPowerShell", "v1.0", "Modules")
    env.setdefault("SYSTEMROOT", system_root)
    return env


def desktop_tools(
    notifier: Notifier,
    *,
    services: Any = psutil,
    min_interval: float = 5.0,
    per_hour: int = 30,
    clock: Callable[[], float] = time.monotonic,
) -> list[Tool[Any]]:
    """notify_desktop (toasts) and service_status. Both only show or read; starting or
    stopping a service goes through run_powershell (``Restart-Service x``)."""

    @tool(risk=Risk.READ_ONLY, timeout=8.0)
    async def service_status(args: ServiceArgs) -> str:
        """Read whether a Windows service is running, how it starts, and what it runs."""
        try:
            info = await asyncio.to_thread(lambda: services.win_service_get(args.name).as_dict())
        except services.NoSuchProcess:
            return f"There is no Windows service named {args.name}."
        except (services.AccessDenied, OSError, AttributeError) as error:
            raise ValueError(f"can't read the service {args.name} ({error})") from error
        text = (
            f"{info.get('name', args.name)} ({info.get('display_name', '')}): "
            f"{info.get('status', 'unknown')}, starts {info.get('start_type', 'unknown')}"
        )
        if info.get("pid"):
            text += f", pid {info['pid']}"
        if info.get("username"):
            text += f", runs as {info['username']}"
        if info.get("binpath"):
            text += f"\ncommand: {str(info['binpath'])[:200]}"
        return text

    notify = notify_tool(
        notifier, desktop="Windows", min_interval=min_interval, per_hour=per_hour, clock=clock
    )
    return [notify, service_status]
