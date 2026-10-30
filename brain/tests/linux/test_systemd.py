"""sd_notify: tell systemd when Zeno is ready, alive and stopping. No-op elsewhere."""

import asyncio
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.api.test_daemon import Log, make_daemon
from zeno.hostos.linux.systemd import SystemdNotifier

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="sd_notify is Linux only")

UNIT = Path(__file__).parents[2] / "daemons" / "zeno.service"


class Systemd:
    """A datagram socket standing in for systemd's notify socket."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(str(path))
        self.sock.setblocking(False)

    def received(self) -> list[str]:
        messages = []
        while True:
            try:
                messages.append(self.sock.recv(4096).decode())
            except BlockingIOError:
                return messages


@pytest.fixture
def systemd(tmp_path: Path) -> Iterator[Systemd]:
    fake = Systemd(tmp_path / "notify")
    yield fake
    fake.sock.close()


def test_without_systemd_every_call_does_nothing() -> None:
    notifier = SystemdNotifier(None)
    assert not notifier.enabled
    assert notifier.ready("up") is False
    assert notifier.watchdog_interval() is None


def test_messages_reach_the_notify_socket(systemd: Systemd) -> None:
    notifier = SystemdNotifier(str(systemd.path))
    assert notifier.ready("Zeno is ready")
    notifier.status("loading model")
    notifier.watchdog()
    notifier.stopping()
    assert systemd.received() == [
        "READY=1\nSTATUS=Zeno is ready",
        "STATUS=loading model",
        "WATCHDOG=1",
        "STOPPING=1",
    ]


def test_status_text_cannot_inject_fields(systemd: Systemd) -> None:
    SystemdNotifier(str(systemd.path)).status("bad\nREADY=1")
    assert systemd.received() == ["STATUS=bad READY=1"]


def test_abstract_socket_addresses_are_supported() -> None:
    name = f"zeno-test-{os.getpid()}"
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
        server.bind("\0" + name)
        assert SystemdNotifier("@" + name).watchdog()
        assert server.recv(100) == b"WATCHDOG=1"


def test_a_vanished_socket_is_not_an_error(tmp_path: Path) -> None:
    assert SystemdNotifier(str(tmp_path / "gone")).ready() is False


@pytest.mark.parametrize(
    ("usec", "pid", "expected"),
    [("60000000", None, 60.0), ("60000000", "1", None), ("0", None, None), ("x", None, None)],
)
def test_watchdog_interval_comes_from_the_environment(
    usec: str, pid: str | None, expected: float | None
) -> None:
    env = {"WATCHDOG_USEC": usec, "WATCHDOG_PID": pid or str(os.getpid())}
    assert SystemdNotifier("/run/notify", env=env).watchdog_interval() == expected


async def test_the_daemon_says_ready_after_boot_and_stopping_at_shutdown(
    tmp_path: Path, systemd: Systemd
) -> None:
    env = {"WATCHDOG_USEC": "60000", "WATCHDOG_PID": str(os.getpid())}  # 60 ms
    log = Log()
    daemon, _ = make_daemon(tmp_path, log)
    daemon.notifier = SystemdNotifier(str(systemd.path), env=env)
    await daemon.start()
    await asyncio.sleep(0.1)
    await daemon.stop()
    messages = systemd.received()
    assert messages[0].startswith("READY=1")
    assert "WATCHDOG=1" in messages
    assert messages[-1] == "STOPPING=1"
    count = messages.count("WATCHDOG=1")
    await asyncio.sleep(0.1)
    assert systemd.received() == [] and count >= 2  # pings stopped with the daemon


async def test_a_failed_boot_reports_why(tmp_path: Path, systemd: Systemd) -> None:
    from tests.api.test_daemon import RecordingEngine

    log = Log()
    daemon, _ = make_daemon(tmp_path, log, RecordingEngine(log, fail=RuntimeError("no model")))
    daemon.notifier = SystemdNotifier(str(systemd.path))
    with pytest.raises(Exception, match="no model"):
        await daemon.start()
    assert systemd.received() == ["STATUS=Zeno could not start: no model"]


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="needs systemd-analyze")
def test_the_unit_file_passes_systemd_verify(tmp_path: Path) -> None:
    unit = tmp_path / "zeno.service"
    text = UNIT.read_text().replace("%h/nexus-2.o/brain/.venv/bin/python", "/usr/bin/true")
    unit.write_text(text)
    env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path)}
    analyze = shutil.which("systemd-analyze")
    assert analyze is not None
    result = subprocess.run(  # noqa: S603 (fixed argv, a test-owned file)
        [analyze, "--user", "verify", str(unit)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        env=env,
    )
    # Unknown keys and bad values are reported against the file, without failing.
    problems = [line for line in result.stderr.splitlines() if str(unit) in line]
    assert result.returncode == 0 and problems == [], result.stderr


def test_the_unit_runs_the_brain_as_a_notify_service() -> None:
    text = UNIT.read_text()
    for line in (
        "Type=notify",
        "ExecStart=%h/nexus-2.o/brain/.venv/bin/python -m zeno serve",
        "Restart=on-failure",
        "WatchdogSec=60",
        "KillMode=mixed",
        "NoNewPrivileges=yes",
        "WantedBy=default.target",
    ):
        assert line in text.splitlines()
