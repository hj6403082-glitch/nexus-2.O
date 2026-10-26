"""D-Bus tools: desktop notifications and read-only systemd unit status."""

from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import ValidationError

from zeno.agent.tools.base import Risk, Tool
from zeno.agent.tools.os_linux import UnitArgs, desktop_tools
from zeno.hostos.desktop import DesktopUnavailable, NotifyArgs, UnitState


@dataclass
class FakeDesktop:
    sent: list[tuple[str, str, str]] = field(default_factory=list)
    units: dict[tuple[str, str], UnitState] = field(default_factory=dict)
    offline: bool = False

    async def notify(self, title: str, body: str, urgency: str) -> int:
        if self.offline:
            raise DesktopUnavailable("no desktop session")
        self.sent.append((title, body, urgency))
        return len(self.sent)

    async def unit_state(self, name: str, scope: str) -> UnitState | None:
        if self.offline:
            raise DesktopUnavailable("no system bus")
        return self.units.get((scope, name))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def tools(desktop: FakeDesktop, clock: Clock | None = None, **limits: Any) -> dict[str, Tool[Any]]:
    found = desktop_tools(desktop, clock=clock or Clock(), **limits)
    return {t.name: t for t in found}


def test_desktop_tools_only_show_or_read() -> None:
    found = tools(FakeDesktop())
    assert sorted(found) == ["notify_desktop", "service_status"]
    assert {t.risk for t in found.values()} == {Risk.READ_ONLY}


@pytest.mark.parametrize(
    "values",
    [
        {"title": ""},
        {"title": "x" * 81},
        {"title": "t", "body": "x" * 401},
        {"title": "t", "urgency": "panic"},
    ],
)
def test_notification_arguments_are_bounded(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        NotifyArgs.model_validate(values)


async def test_a_notification_reaches_the_desktop() -> None:
    desktop = FakeDesktop()
    text = await tools(desktop)["notify_desktop"].invoke(
        NotifyArgs(title="Backup done", body="All 3 folders copied.", urgency="low")
    )
    assert desktop.sent == [("Backup done", "All 3 folders copied.", "low")]
    assert "shown" in text


async def test_notifications_are_rate_limited() -> None:
    desktop, clock = FakeDesktop(), Clock()
    notify = tools(desktop, clock, min_interval=5.0, per_hour=3)["notify_desktop"]
    await notify.invoke(NotifyArgs(title="one"))
    with pytest.raises(ValueError, match="wait"):
        await notify.invoke(NotifyArgs(title="too soon"))
    for title in ("two", "three"):
        clock.now += 6
        await notify.invoke(NotifyArgs(title=title))
    clock.now += 6
    with pytest.raises(ValueError, match="hour"):
        await notify.invoke(NotifyArgs(title="four"))
    clock.now += 3600
    await notify.invoke(NotifyArgs(title="next hour"))
    assert [s[0] for s in desktop.sent] == ["one", "two", "three", "next hour"]


async def test_no_desktop_session_is_a_plain_answer() -> None:
    with pytest.raises(ValueError, match="no desktop session"):
        await tools(FakeDesktop(offline=True))["notify_desktop"].invoke(NotifyArgs(title="hi"))


@pytest.mark.parametrize(
    "name", ["nginx", "a b.service", "../x.service", "x.service;rm", "x" * 120 + ".service"]
)
def test_unit_names_are_validated(name: str) -> None:
    with pytest.raises(ValidationError):
        UnitArgs(name=name)


async def test_service_status_reads_the_unit() -> None:
    desktop = FakeDesktop(
        units={
            ("system", "nginx.service"): UnitState(
                "nginx.service", "A web server", "loaded", "failed", "failed", 1_700_000_000.0
            )
        }
    )
    text = await tools(desktop)["service_status"].invoke(UnitArgs(name="nginx.service"))
    assert text.startswith("nginx.service (A web server): failed (failed), loaded")
    assert "since" in text


async def test_service_status_for_an_unknown_unit() -> None:
    text = await tools(FakeDesktop())["service_status"].invoke(
        UnitArgs(name="nope.service", scope="user")
    )
    assert "not loaded" in text
