"""Pick this machine's OS toolset at boot: one ``platform.system()`` check, one import.

``os_linux`` and ``os_windows`` are imported only inside the branch for their OS, so
a Linux boot never loads Windows code or WinRT, and a Windows boot never loads Linux
code or dbus-fast. Telemetry (psutil) is shared. Any other OS gets telemetry only.
"""

import logging
import platform
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from zeno.agent.tools.base import Tool
from zeno.agent.tools.telemetry import telemetry_tools
from zeno.config import Settings
from zeno.hostos.process import CommandSettings

log = logging.getLogger(__name__)

HostOs = Literal["linux", "windows", "other"]


@dataclass(slots=True)
class OsToolset:
    tools: list[Tool[Any]] = field(default_factory=list)
    cleanups: list[Callable[[], Any]] = field(default_factory=list)
    """Called (and awaited when they return an awaitable) when the daemon stops."""


class ServiceNotifier(Protocol):
    """Tells the OS service manager how Zeno is doing (systemd on Linux)."""

    def ready(self, status: str = "") -> bool: ...

    def status(self, text: str) -> bool: ...

    def watchdog(self) -> bool: ...

    def stopping(self) -> bool: ...

    def watchdog_interval(self) -> float | None: ...


class NullNotifier:
    """For systems whose service manager takes no status (Windows Task Scheduler)."""

    def ready(self, status: str = "") -> bool:
        return False

    def status(self, text: str) -> bool:
        return False

    def watchdog(self) -> bool:
        return False

    def stopping(self) -> bool:
        return False

    def watchdog_interval(self) -> float | None:
        return None


def host_os(system: Callable[[], str] | None = None) -> HostOs:
    name = (system or platform.system)()
    if name == "Linux":
        return "linux"
    if name == "Windows":
        return "windows"
    return "other"


def command_settings(settings: Settings) -> CommandSettings:
    return CommandSettings(
        roots=settings.run_command_roots,
        default_timeout=settings.run_command_timeout,
        max_output=settings.run_command_max_output,
    )


def load_os_tools(settings: Settings, *, system: Callable[[], str] | None = None) -> OsToolset:
    """The tools for this OS that the owner turned on; nothing when both switches are off."""
    if not (settings.os_tools or settings.run_command):
        return OsToolset()
    match host_os(system):
        case "linux":
            from zeno.agent.tools import os_linux

            return os_linux.linux_tools(settings, command_settings(settings))
        case "windows":
            from zeno.agent.tools import os_windows

            return os_windows.windows_tools(settings, command_settings(settings))
        case _:
            log.warning(
                "%s has no OS toolset: only telemetry is offered, and ZENO_RUN_COMMAND is ignored",
                (system or platform.system)() or "this OS",
            )
            return OsToolset(telemetry_tools() if settings.os_tools else [])


def service_notifier(system: Callable[[], str] | None = None) -> ServiceNotifier:
    if host_os(system) == "linux":
        from zeno.hostos.linux.systemd import SystemdNotifier

        return SystemdNotifier.from_environment()
    return NullNotifier()
