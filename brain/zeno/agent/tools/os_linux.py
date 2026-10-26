"""Zeno's Linux toolset: run_command, notify_desktop (D-Bus) and service_status (systemd).

run_command has no shell. The command line is split into an argument list by the
command policy, which refuses dangerous commands before the owner is even asked (the
tool's ``precheck``). An approved command starts with ``create_subprocess_exec`` in
its own process group, with stdin closed, a small environment and a time limit.
stdout and stderr come back separately with the exit code, so Zeno can read its own
errors.

Nothing here imports Windows code; ``os_loader`` loads this module on Linux only.
"""

import os
import posixpath
import shutil
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path, PurePath
from typing import Annotated, Any, Literal, Protocol

from pydantic import AfterValidator, Field, StringConstraints

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool
from zeno.agent.tools.os_loader import OsToolset
from zeno.agent.tools.telemetry import telemetry_tools
from zeno.config import Settings
from zeno.hostos.desktop import DesktopUnavailable, Notifier, Scope, UnitState, notify_tool
from zeno.hostos.linux.command_policy import TRUSTED_DIRS, PolicyContext, check_command
from zeno.hostos.linux.process import run_linux_process
from zeno.hostos.process import (
    KILL_GRACE,
    CommandRefused,
    CommandSettings,
    Runner,
    one_line,
    report,
)

__all__ = [
    "CommandArgs",
    "CommandSettings",
    "LinuxDesktop",
    "UnitArgs",
    "command_tools",
    "desktop_tools",
    "linux_tools",
    "trusted_which",
]

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

UnitName = Annotated[
    str,
    StringConstraints(
        pattern=r"^[A-Za-z0-9@._-]{1,100}\.(service|timer|socket|mount|target|path)$"
    ),
]


class CommandArgs(ToolArgs):
    command: Annotated[str, Field(min_length=1, max_length=1000), AfterValidator(one_line)]
    cwd: str | None = Field(
        None, max_length=500, description="Working folder; defaults to the home folder."
    )
    timeout: int | None = Field(None, ge=1, le=120, description="Seconds before it is stopped.")


class UnitArgs(ToolArgs):
    name: UnitName = Field(description="A unit such as nginx.service.")
    scope: Literal["system", "user"] = "system"


class LinuxDesktop(Notifier, Protocol):
    async def unit_state(self, name: str, scope: Scope) -> UnitState | None: ...


def linux_tools(
    settings: Settings, command: CommandSettings, *, desktop: LinuxDesktop | None = None
) -> OsToolset:
    """What ``os_loader`` registers on Linux, as the owner's settings turn it on."""
    toolset = OsToolset()
    if settings.os_tools:
        if desktop is None:
            from zeno.hostos.linux.dbus import DbusDesktop  # dbus-fast is on Linux only

            dbus = DbusDesktop()
            toolset.cleanups.append(dbus.close)
            desktop = dbus
        toolset.tools += telemetry_tools()
        toolset.tools += desktop_tools(desktop, per_hour=settings.desktop_notify_per_hour)
    if settings.run_command:
        toolset.tools += command_tools(command)
    return toolset


def trusted_which(name: str) -> str | None:
    """Find a program in the trusted system folders only; PATH is ignored."""
    return shutil.which(name, path=":".join(TRUSTED_DIRS))


def command_tools(
    settings: CommandSettings,
    *,
    runner: Runner | None = None,
    which: Callable[[str], str | None] = trusted_which,
    home: str | None = None,
    realpath: Callable[[str], str] = os.path.realpath,
    isdir: Callable[[str], bool] = os.path.isdir,
) -> list[Tool[Any]]:
    """run_command. Paths are POSIX strings throughout, and the file system calls are
    passed in, so the tool's tests run on any OS."""
    run = runner or run_linux_process
    home_dir = home or PurePath(Path.home()).as_posix()
    roots = [realpath(_expand(PurePath(root).as_posix(), home_dir)) for root in settings.roots]

    def plan(args: CommandArgs) -> tuple[list[str], str]:
        """The checked argv and working folder, or ``CommandRefused``."""
        folder = _expand(args.cwd or home_dir, home_dir)
        real = realpath(posixpath.join(home_dir, folder))  # an absolute folder wins the join
        if not isdir(real) or not any(_within(real, root) for root in roots):
            raise CommandRefused(
                f"the working folder {args.cwd or home_dir} is not an existing folder inside "
                f"{', '.join(roots)}"
            )
        context = PolicyContext(
            home=home_dir,
            cwd=real,
            own_pid=os.getpid(),
            which=which,
            realpath=realpath,
        )
        return check_command(args.command, context), real

    def precheck(args: CommandArgs) -> str | None:
        try:
            plan(args)
        except CommandRefused as refusal:
            return str(refusal)
        return None

    # Outlasts the longest allowed command, so the runner's own timeout is reported.
    @tool(risk=Risk.PRIVILEGED, timeout=120 + KILL_GRACE + 5.0, precheck=precheck)
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
        return report("run_command", result, timeout)

    return [run_command]


def _expand(path: str, home: str) -> str:
    if path == "~" or path.startswith("~/"):
        return home + path[1:]
    return path


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _environment() -> dict[str, str]:
    env = {key: os.environ[key] for key in _ENV_KEYS if key in os.environ}
    env["PATH"] = ":".join(TRUSTED_DIRS)
    env["TERM"] = "dumb"
    return env


def desktop_tools(
    desktop: LinuxDesktop,
    *,
    min_interval: float = 5.0,
    per_hour: int = 30,
    clock: Callable[[], float] = time.monotonic,
) -> list[Tool[Any]]:
    """notify_desktop and service_status over D-Bus. Both only show or read; starting or
    stopping a unit goes through run_command (``systemctl --user restart x``)."""

    @tool(risk=Risk.READ_ONLY, timeout=8.0)
    async def service_status(args: UnitArgs) -> str:
        """Read whether a systemd service (or timer, socket...) is running, and since when."""
        try:
            state = await desktop.unit_state(args.name, args.scope)
        except DesktopUnavailable as error:
            raise ValueError(str(error)) from error
        if state is None:
            return f"{args.name} is not loaded in the {args.scope} systemd."
        text = f"{state.name} ({state.description}): {state.active} ({state.sub}), {state.load}"
        if state.since is not None:
            since = datetime.fromtimestamp(state.since).astimezone()
            text += f", since {since.isoformat(timespec='seconds')}"
        return text

    notify = notify_tool(
        desktop, desktop="Linux", min_interval=min_interval, per_hour=per_hour, clock=clock
    )
    return [notify, service_status]
