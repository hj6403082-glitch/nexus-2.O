"""Date and time."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field

from zeno.agent.tools.base import Risk, ToolArgs, tool


class TimeArgs(ToolArgs):
    timezone: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+)*$",
        description="IANA time zone such as Europe/London; leave out for local time.",
    )


@tool(risk=Risk.READ_ONLY, timeout=2.0)
async def get_time(args: TimeArgs) -> str:
    """Get the current date, time and weekday, locally or in a given time zone."""
    if args.timezone is None:
        now = datetime.now().astimezone()
        zone = now.tzname() or "local time"
    else:
        try:
            now = datetime.now(ZoneInfo(args.timezone))
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"Unknown time zone {args.timezone!r}.") from None
        zone = args.timezone
    return f"{now.isoformat(timespec='seconds')} ({now:%A}, {zone})"
