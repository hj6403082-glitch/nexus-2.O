"""What the desktop tools share on every OS: errors, unit state and notification limits."""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import Field

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool

Scope = Literal["system", "user"]
URGENCY = {"low": 0, "normal": 1, "critical": 2}


class DesktopUnavailable(Exception):
    """The desktop, bus or service manager can't be reached."""


@dataclass(frozen=True, slots=True)
class UnitState:
    name: str
    description: str
    load: str
    active: str
    sub: str
    since: float | None
    """When it entered this state (Unix time), if the OS recorded it."""


class Notifier(Protocol):
    async def notify(self, title: str, body: str, urgency: str) -> object: ...


class NotifyArgs(ToolArgs):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field("", max_length=400)
    urgency: Literal["low", "normal", "critical"] = "normal"


def notify_tool(
    notifier: Notifier,
    *,
    desktop: str,
    min_interval: float = 5.0,
    per_hour: int = 30,
    clock: Callable[[], float] = time.monotonic,
) -> Tool[Any]:
    """``notify_desktop``, rate-limited the same way on every OS."""
    sent: deque[float] = deque()

    async def notify_desktop(args: NotifyArgs) -> str:
        now = clock()
        while sent and now - sent[0] >= 3600:
            sent.popleft()
        if sent and now - sent[-1] < min_interval:
            raise ValueError(f"wait {min_interval - (now - sent[-1]):.0f} s between notifications")
        if len(sent) >= per_hour:
            raise ValueError(f"the limit of {per_hour} notifications an hour is reached")
        try:
            await notifier.notify(args.title, args.body, args.urgency)
        except DesktopUnavailable as error:
            raise ValueError(str(error)) from error
        sent.append(now)
        return f"Notification shown: {args.title}"

    notify_desktop.__doc__ = f"Show a notification on the owner's {desktop} desktop."
    return tool(risk=Risk.READ_ONLY, timeout=8.0)(notify_desktop)
