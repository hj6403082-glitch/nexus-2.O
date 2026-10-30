"""DbusDesktop against a real, private dbus-daemon with stand-in services.

The test starts its own session bus, so nothing reaches the machine's desktop or
systemd. It is skipped where dbus-daemon is not installed.
"""

import contextlib
import shutil
import subprocess
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from dbus_fast import BusType, DBusError, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.constants import PropertyAccess
from dbus_fast.service import ServiceInterface, dbus_property, method

from zeno.hostos.linux.dbus import DbusDesktop, DesktopUnavailable

DAEMON = shutil.which("dbus-daemon")
pytestmark = pytest.mark.skipif(DAEMON is None, reason="needs dbus-daemon")


class Notifications(ServiceInterface):
    def __init__(self) -> None:
        super().__init__("org.freedesktop.Notifications")
        self.received: list[list[Any]] = []

    @method()
    def Notify(
        self,
        app: "s",
        replaces: "u",
        icon: "s",
        summary: "s",
        body: "s",
        actions: "as",
        hints: "a{sv}",
        timeout: "i",
    ) -> "u":
        self.received.append([app, summary, body, hints["urgency"].value, timeout])
        return 7


class Manager(ServiceInterface):
    def __init__(self) -> None:
        super().__init__("org.freedesktop.systemd1.Manager")

    @method()
    def GetUnit(self, name: "s") -> "o":
        if name != "nginx.service":
            raise DBusError("org.freedesktop.systemd1.NoSuchUnit", f"Unit {name} not loaded.")
        return "/org/freedesktop/systemd1/unit/nginx_2eservice"


class Unit(ServiceInterface):
    def __init__(self) -> None:
        super().__init__("org.freedesktop.systemd1.Unit")

    @dbus_property(access=PropertyAccess.READ)
    def Id(self) -> "s":
        return "nginx.service"

    @dbus_property(access=PropertyAccess.READ)
    def Description(self) -> "s":
        return "A web server"

    @dbus_property(access=PropertyAccess.READ)
    def LoadState(self) -> "s":
        return "loaded"

    @dbus_property(access=PropertyAccess.READ)
    def ActiveState(self) -> "s":
        return "active"

    @dbus_property(access=PropertyAccess.READ)
    def SubState(self) -> "s":
        return "running"

    @dbus_property(access=PropertyAccess.READ)
    def StateChangeTimestamp(self) -> "t":
        return 1_700_000_000_000_000


@pytest.fixture
def bus_address() -> Iterator[str]:
    assert DAEMON is not None
    process = subprocess.Popen(  # noqa: S603 (fixed argv)
        [DAEMON, "--session", "--nofork", "--print-address"],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    address = process.stdout.readline().strip()
    try:
        yield address
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.fixture
async def services(bus_address: str) -> AsyncIterator[Notifications]:
    bus = await MessageBus(bus_address=bus_address).connect()
    notifications = Notifications()
    bus.export("/org/freedesktop/Notifications", notifications)
    bus.export("/org/freedesktop/systemd1", Manager())
    bus.export("/org/freedesktop/systemd1/unit/nginx_2eservice", Unit())
    await bus.request_name("org.freedesktop.Notifications")
    await bus.request_name("org.freedesktop.systemd1")
    try:
        yield notifications
    finally:
        bus.disconnect()


async def test_notify_calls_the_notification_service(
    bus_address: str, services: Notifications
) -> None:
    desktop = DbusDesktop(session_address=bus_address, system_address=bus_address)
    try:
        assert await desktop.notify("Hello", "From Zeno", "critical") == 7
    finally:
        await desktop.close()
    assert services.received == [["Zeno", "Hello", "From Zeno", 2, -1]]


async def test_unit_state_reads_systemd_properties(
    bus_address: str, services: Notifications
) -> None:
    desktop = DbusDesktop(session_address=bus_address, system_address=bus_address)
    try:
        state = await desktop.unit_state("nginx.service", "system")
        assert state is not None
        assert (state.active, state.sub, state.load) == ("active", "running", "loaded")
        assert state.since == 1_700_000_000.0
        assert await desktop.unit_state("nope.service", "user") is None
    finally:
        await desktop.close()


async def test_a_missing_bus_is_reported_not_raised_raw(tmp_path: Any) -> None:
    desktop = DbusDesktop(
        session_address=f"unix:path={tmp_path}/none", system_address=f"unix:path={tmp_path}/none"
    )
    with pytest.raises(DesktopUnavailable):
        await desktop.notify("x", "", "normal")
    with contextlib.suppress(Exception):
        await desktop.close()


def test_bus_types_are_what_we_expect() -> None:
    assert BusType.SESSION != BusType.SYSTEM and Variant("y", 1).signature == "y"
