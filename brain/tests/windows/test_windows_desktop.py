"""Windows toasts (WinRT, faked) and read-only service status (psutil, faked)."""

import asyncio
import sys
import xml.dom.minidom
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import psutil
import pytest

from zeno.agent.tools.base import Risk, Tool
from zeno.agent.tools.os_windows import ServiceArgs, desktop_tools
from zeno.hostos.desktop import DesktopUnavailable, NotifyArgs
from zeno.hostos.windows import process as winproc
from zeno.hostos.windows.toast import APP_ID, POWERSHELL_APP_ID, WindowsToaster, toast_xml


@dataclass
class FakeWinRT:
    """The few WinRT classes the toaster uses, recording what they are asked."""

    setting: int = 0
    shown: list[tuple[str, str]] = field(default_factory=list)
    fail: bool = False

    def modules(self) -> tuple[Any, Any]:
        fake = self

        class XmlDocument:
            def __init__(self) -> None:
                self.xml = ""

            def load_xml(self, text: str) -> None:
                xml.dom.minidom.parseString(text)  # noqa: S318 - our own XML; fails like WinRT
                self.xml = text

        class ToastNotification:
            def __init__(self, document: XmlDocument) -> None:
                self.document = document

        class Notifier:
            def __init__(self, app_id: str) -> None:
                self.app_id = app_id
                self.setting = fake.setting

            def show(self, toast: ToastNotification) -> None:
                if fake.fail:
                    raise OSError(-2147024891, "Access is denied")
                fake.shown.append((self.app_id, toast.document.xml))

        manager = SimpleNamespace(create_toast_notifier_with_id=Notifier)
        dom = SimpleNamespace(XmlDocument=XmlDocument)
        notifications = SimpleNamespace(
            ToastNotificationManager=manager, ToastNotification=ToastNotification
        )
        return dom, notifications


async def test_a_toast_is_shown_under_zenos_id() -> None:
    winrt = FakeWinRT()
    toaster = WindowsToaster(registered=lambda: True, winrt=winrt.modules)
    await toaster.notify("Disk almost full", "C: is 95% used <check>", "normal")
    ((app_id, shown),) = winrt.shown
    assert app_id == APP_ID
    assert "<text>Disk almost full</text>" in shown and "&lt;check&gt;" in shown


async def test_without_the_shortcut_the_toast_uses_powershells_id() -> None:
    winrt = FakeWinRT()
    await WindowsToaster(registered=lambda: False, winrt=winrt.modules).notify("t", "", "normal")
    assert winrt.shown[0][0] == POWERSHELL_APP_ID


@pytest.mark.parametrize(
    ("urgency", "present", "absent"),
    [
        ("critical", 'scenario="urgent"', 'silent="true"'),
        ("low", 'silent="true"', "scenario"),
        ("normal", "<toast>", "silent"),
    ],
)
def test_urgency_maps_to_the_toast(urgency: str, present: str, absent: str) -> None:
    text = toast_xml("Title & more", "", urgency)
    xml.dom.minidom.parseString(text)  # noqa: S318 - our own XML
    assert present in text and absent not in text and "Title &amp; more" in text


@pytest.mark.parametrize(
    ("winrt", "reason"),
    [(FakeWinRT(setting=2), "turned off"), (FakeWinRT(fail=True), "refused")],
)
async def test_windows_refusals_are_plain_reasons(winrt: FakeWinRT, reason: str) -> None:
    toaster = WindowsToaster(registered=lambda: True, winrt=winrt.modules)
    with pytest.raises(DesktopUnavailable, match=reason):
        await toaster.notify("t", "b", "normal")


async def test_without_winrt_notifications_are_unavailable() -> None:
    def missing() -> tuple[Any, Any]:
        raise ImportError("No module named 'winrt'")

    toaster = WindowsToaster(registered=lambda: True, winrt=missing)
    with pytest.raises(DesktopUnavailable, match="winrt"):
        await toaster.notify("t", "b", "normal")


# --- the tools --------------------------------------------------------------------------


@dataclass
class FakeServices:
    NoSuchProcess: type[Exception] = psutil.NoSuchProcess
    AccessDenied: type[Exception] = psutil.AccessDenied
    services: dict[str, dict[str, Any]] = field(default_factory=dict)

    def win_service_get(self, name: str) -> Any:
        if name not in self.services:
            raise psutil.NoSuchProcess(pid=None, name=name, msg="service not found")
        return SimpleNamespace(as_dict=lambda: self.services[name])


SPOOLER = {
    "name": "Spooler",
    "display_name": "Print Spooler",
    "status": "running",
    "start_type": "automatic",
    "pid": 2112,
    "username": "LocalSystem",
    "binpath": "C:\\Windows\\System32\\spoolsv.exe",
}


@dataclass
class FakeToaster:
    sent: list[tuple[str, str, str]] = field(default_factory=list)

    async def notify(self, title: str, body: str, urgency: str) -> int:
        self.sent.append((title, body, urgency))
        return 0


def tools(**overrides: Any) -> dict[str, Tool[Any]]:
    found = desktop_tools(
        overrides.pop("notifier", FakeToaster()),
        services=overrides.pop("services", FakeServices(services={"Spooler": SPOOLER})),
        **overrides,
    )
    return {t.name: t for t in found}


def test_the_windows_desktop_tools_match_linux_by_name_and_only_read() -> None:
    found = tools()
    assert set(found) == {"notify_desktop", "service_status"}
    assert all(t.risk is Risk.READ_ONLY for t in found.values())
    assert "Windows" in found["notify_desktop"].description


async def test_service_status_reads_a_service() -> None:
    text = await tools()["service_status"].invoke(ServiceArgs(name="Spooler"))
    assert text.startswith("Spooler (Print Spooler): running, starts automatic, pid 2112")
    assert "spoolsv.exe" in text


async def test_service_status_for_a_missing_service() -> None:
    text = await tools()["service_status"].invoke(ServiceArgs(name="nope"))
    assert text == "There is no Windows service named nope."


@pytest.mark.parametrize("name", ["", "a b", "x;y", "..\\x", "a" * 81])
def test_service_names_are_checked(name: str) -> None:
    with pytest.raises(ValueError):
        ServiceArgs(name=name)


async def test_notify_desktop_is_rate_limited_like_linux() -> None:
    toaster = FakeToaster()
    notify = tools(notifier=toaster, per_hour=1, clock=lambda: 50.0)["notify_desktop"]
    assert await notify.invoke(NotifyArgs(title="hi")) == "Notification shown: hi"
    with pytest.raises(ValueError, match="wait"):
        await notify.invoke(NotifyArgs(title="again"))
    assert toaster.sent == [("hi", "", "normal")]


# --- the runner's tree kill -------------------------------------------------------------


@dataclass
class FakeProc:
    pid: int
    killed: list[int]
    kids: list["FakeProc"] = field(default_factory=list)

    def children(self, recursive: bool = False) -> list["FakeProc"]:
        assert recursive
        return self.kids

    def kill(self) -> None:
        self.killed.append(self.pid)


async def test_a_timeout_kills_the_whole_tree_children_first() -> None:
    killed: list[int] = []
    tree = FakeProc(10, killed, [FakeProc(11, killed), FakeProc(12, killed)])
    ps = SimpleNamespace(
        Process=lambda pid: tree,
        NoSuchProcess=psutil.NoSuchProcess,
        AccessDenied=psutil.AccessDenied,
    )

    class Process:
        pid = 10

        async def wait(self) -> int:
            return 1

    await winproc.stop_tree(Process(), ps=ps)  # type: ignore[arg-type]
    assert killed == [11, 12, 10]


def test_windows_commands_start_without_a_console_window() -> None:
    options = winproc.spawn_options()
    if sys.platform == "win32":
        assert options == {"creationflags": 0x08000200}
    else:
        assert options == {"start_new_session": True}


@pytest.mark.skipif(sys.platform != "win32", reason="runs a real Windows program")
async def test_the_real_windows_runner_captures_both_streams(tmp_path: Any) -> None:
    result = await winproc.run_windows_process(
        ["cmd.exe", "/c", "echo out & echo err 1>&2 & exit 3"],
        cwd=str(tmp_path),
        seconds=20,
        env={"SYSTEMROOT": "C:\\Windows"},
        max_output=200,
    )
    assert result.exit_code == 3 and "out" in result.stdout and "err" in result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="runs a real Windows program")
async def test_the_real_windows_runner_kills_on_timeout(tmp_path: Any) -> None:
    result = await winproc.run_windows_process(
        ["ping.exe", "-n", "30", "127.0.0.1"],
        cwd=str(tmp_path),
        seconds=1,
        env={"SYSTEMROOT": "C:\\Windows"},
        max_output=200,
    )
    assert result.killed and result.elapsed < 10
    await asyncio.sleep(0)


def test_the_toast_identity_is_looked_up_only_on_windows() -> None:
    from zeno.hostos.windows.toast import REGISTRATION, app_id_registered

    assert REGISTRATION == "Software\\Classes\\AppUserModelId\\Zeno.Brain"
    if sys.platform != "win32":
        assert app_id_registered() is False
