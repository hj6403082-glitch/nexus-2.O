"""Desktop tools over D-Bus: show a notification, read a systemd unit's state.

Both only show or read. Starting or stopping a unit goes through ``run_command``
(``systemctl --user restart x``), which needs the owner's approval.
"""

import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol

from pydantic import Field, StringConstraints

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool
from zeno.desktop.dbus import DesktopUnavailable, Scope, UnitState

UnitName = Annotated[
    str,
    StringConstraints(
        pattern=r"^[A-Za-z0-9@._-]{1,100}\.(service|timer|socket|mount|target|path)$"
    ),
]


class Desktop(Protocol):
    async def notify(self, title: str, body: str, urgency: str) -> int: ...

    async def unit_state(self, name: str, scope: Scope) -> UnitState | None: ...


class NotifyArgs(ToolArgs):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field("", max_length=400)
    urgency: Literal["low", "normal", "critical"] = "normal"


class UnitArgs(ToolArgs):
    name: UnitName = Field(description="A unit such as nginx.service.")
    scope: Literal["system", "user"] = "system"


def desktop_tools(
    desktop: Desktop,
    *,
    min_interval: float = 5.0,
    per_hour: int = 30,
    clock: Callable[[], float] = time.monotonic,
) -> list[Tool[Any]]:
    sent: deque[float] = deque()

    @tool(risk=Risk.READ_ONLY, timeout=8.0)
    async def notify_desktop(args: NotifyArgs) -> str:
        """Show a notification on the owner's Linux desktop."""
        now = clock()
        while sent and now - sent[0] >= 3600:
            sent.popleft()
        if sent and now - sent[-1] < min_interval:
            raise ValueError(f"wait {min_interval - (now - sent[-1]):.0f} s between notifications")
        if len(sent) >= per_hour:
            raise ValueError(f"the limit of {per_hour} notifications an hour is reached")
        try:
            await desktop.notify(args.title, args.body, args.urgency)
        except DesktopUnavailable as error:
            raise ValueError(str(error)) from error
        sent.append(now)
        return f"Notification shown: {args.title}"

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

    return [notify_desktop, service_status]
