"""Telemetry tools: system health, temperatures and processes, read through psutil."""

import time
from collections import namedtuple
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import psutil
import pytest
from pydantic import ValidationError

from zeno.agent.tools.base import Risk, Tool
from zeno.agent.tools.telemetry import (
    HealthArgs,
    ProcessArgs,
    TemperatureArgs,
    TopArgs,
    telemetry_tools,
)

Mem = namedtuple("Mem", "total available percent")
Swap = namedtuple("Swap", "total used percent")
Part = namedtuple("Part", "device mountpoint fstype opts", defaults=["rw"])
Usage = namedtuple("Usage", "total used percent")
Battery = namedtuple("Battery", "percent power_plugged secsleft")
Temp = namedtuple("Temp", "label current high critical")
Fan = namedtuple("Fan", "label current")
MemInfo = namedtuple("MemInfo", "rss")

GB = 1024**3


@dataclass
class FakeProcess:
    pid: int
    pname: str
    cpu: float
    rss: int
    user: str = "boss"
    gone: bool = False
    denied: bool = False
    calls: int = 0
    info: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.info = {
            "pid": self.pid,
            "name": self.pname,
            "username": self.user,
            "memory_info": MemInfo(self.rss),
            "status": "running",
        }

    def cpu_percent(self, interval: float | None = None) -> float:
        if self.gone:
            raise psutil.NoSuchProcess(self.pid)
        self.calls += 1
        return 0.0 if self.calls == 1 and interval is None else self.cpu

    # process_info
    def oneshot(self) -> Any:
        from contextlib import nullcontext

        return nullcontext()

    def name(self) -> str:
        return self.pname

    def username(self) -> str:
        if self.denied:
            raise psutil.AccessDenied(self.pid)
        return self.user

    def status(self) -> str:
        return "sleeping"

    def create_time(self) -> float:
        return time.time() - 3600

    def num_threads(self) -> int:
        return 7

    def ppid(self) -> int:
        return 1

    def cmdline(self) -> list[str]:
        return ["/usr/bin/" + self.pname, "--flag", "x" * 400]

    def memory_info(self) -> MemInfo:
        return MemInfo(self.rss)


def fake_psutil(**overrides: Any) -> Any:
    procs = [
        FakeProcess(10, "firefox", cpu=40.0, rss=2 * GB),
        FakeProcess(20, "llama", cpu=90.0, rss=6 * GB),
        FakeProcess(30, "sshd", cpu=0.1, rss=10_000_000),
        FakeProcess(40, "gone", cpu=5.0, rss=1, gone=True),
    ]
    module = SimpleNamespace(
        NoSuchProcess=psutil.NoSuchProcess,
        AccessDenied=psutil.AccessDenied,
        ZombieProcess=psutil.ZombieProcess,
        cpu_percent=lambda interval=None: 23.5,
        cpu_count=lambda logical=True: 8,
        getloadavg=lambda: (1.5, 1.0, 0.5),
        virtual_memory=lambda: Mem(16 * GB, 6 * GB, 62.5),
        swap_memory=lambda: Swap(2 * GB, 0, 0.0),
        disk_partitions=lambda all=False: [
            Part("/dev/nvme0n1p2", "/", "ext4"),
            Part("/dev/nvme0n1p1", "/boot/efi", "vfat"),
        ],
        disk_usage=lambda path: (
            Usage(500 * GB, 400 * GB, 80.0) if path == "/" else Usage(GB, GB // 10, 10.0)
        ),
        boot_time=lambda: time.time() - (2 * 86400 + 3 * 3600 + 60),
        sensors_battery=lambda: Battery(76.0, False, 7200),
        sensors_temperatures=lambda fahrenheit=False: {
            "coretemp": [
                Temp("Package id 0", 71.0, 80.0, 100.0),
                Temp("Core 0", 88.0, 80.0, 100.0),
            ],
            "nvme": [Temp("Composite", 45.0, None, None)],
        },
        sensors_fans=lambda: {"thinkpad": [Fan("fan1", 2400)]},
        process_iter=lambda attrs=None: iter(procs),
        Process=lambda pid: (
            next(p for p in procs if p.pid == pid)
            if pid in (10, 20, 30)
            else (_raise(psutil.NoSuchProcess(pid)))
        ),
        procs=procs,
    )
    for key, value in overrides.items():
        setattr(module, key, value)
    return module


def _raise(error: Exception) -> Any:
    raise error


def tools(ps: Any = None) -> dict[str, Tool[Any]]:
    found = telemetry_tools(ps=ps or fake_psutil(), sample_seconds=0.0)
    return {t.name: t for t in found}


def test_the_telemetry_tools_only_look() -> None:
    found = tools()
    assert sorted(found) == [
        "process_info",
        "system_health",
        "system_temperatures",
        "top_processes",
    ]
    assert {t.risk for t in found.values()} == {Risk.READ_ONLY}


async def test_system_health_summarises_the_machine() -> None:
    text = await tools()["system_health"].invoke(HealthArgs())
    assert "CPU 23.5% of 8 cores" in text
    assert "load 1.50 1.00 0.50" in text
    assert "memory 62.5% used (6.0 GB of 16.0 GB free)" in text
    assert "/ 80.0% used (400.0 GB of 500.0 GB)" in text and "/boot/efi" in text
    assert "up 2 days 3 h" in text
    assert "battery 76% (on battery, 2 h 0 min left)" in text


async def test_health_without_battery_or_load_average() -> None:
    ps = fake_psutil(sensors_battery=lambda: None)
    del ps.getloadavg
    text = await tools(ps)["system_health"].invoke(HealthArgs())
    assert "battery" not in text and "load" not in text


async def test_temperatures_flag_hot_sensors() -> None:
    text = await tools()["system_temperatures"].invoke(TemperatureArgs())
    assert "coretemp Package id 0: 71.0 °C" in text
    assert "Core 0: 88.0 °C (above high 80)" in text
    assert "nvme Composite: 45.0 °C" in text
    assert "fan1: 2400 RPM" in text


async def test_temperatures_where_the_platform_has_none() -> None:
    ps = fake_psutil()
    del ps.sensors_temperatures
    del ps.sensors_fans
    text = await tools(ps)["system_temperatures"].invoke(TemperatureArgs())
    assert "No temperature sensors" in text


async def test_top_processes_by_cpu_skips_vanished_ones() -> None:
    text = await tools()["top_processes"].invoke(TopArgs(sort_by="cpu", limit=2))
    lines = text.splitlines()
    assert "llama" in lines[1] and "90.0%" in lines[1]
    assert "firefox" in lines[2]
    assert "gone" not in text and "sshd" not in text


async def test_top_processes_by_memory() -> None:
    text = await tools()["top_processes"].invoke(TopArgs(sort_by="memory", limit=3))
    names = [line.split()[1] for line in text.splitlines()[1:]]
    assert names == ["llama", "firefox", "sshd"]
    assert "--flag" not in text  # no command lines in the overview


@pytest.mark.parametrize("limit", [0, 21])
def test_top_limit_is_bounded(limit: int) -> None:
    with pytest.raises(ValidationError):
        TopArgs(limit=limit)


async def test_process_info_describes_one_process() -> None:
    text = await tools()["process_info"].invoke(ProcessArgs(pid=20))
    assert "llama (pid 20)" in text and "user boss" in text and "threads 7" in text
    assert "parent 1" in text and "6.0 GB" in text
    command = next(line for line in text.splitlines() if line.startswith("command:"))
    assert len(command) <= 220 and command.endswith("…")


async def test_process_info_for_a_missing_process() -> None:
    with pytest.raises(ValueError, match="no process 999"):
        await tools()["process_info"].invoke(ProcessArgs(pid=999))


async def test_process_info_when_access_is_denied() -> None:
    ps = fake_psutil()
    ps.procs[0].denied = True
    text = await tools(ps)["process_info"].invoke(ProcessArgs(pid=10))
    assert "user unknown" in text


async def test_the_real_psutil_works_here() -> None:
    found = {t.name: t for t in telemetry_tools(sample_seconds=0.05)}
    assert "CPU" in await found["system_health"].invoke(HealthArgs())
    assert "pid" in await found["top_processes"].invoke(TopArgs(limit=3))


# --- the same tools on a Windows-shaped psutil ----------------------------------------


def windows_psutil() -> Any:
    def usage(path: str) -> Usage:
        if path != "C:\\":
            raise PermissionError(path)  # what psutil raises for an empty drive
        return Usage(500 * GB, 200 * GB, 40.0)

    module = fake_psutil(
        disk_partitions=lambda all=False: [
            Part("C:\\", "C:\\", "NTFS", "rw,fixed"),
            Part("D:\\", "D:\\", "", "cdrom"),
            Part("E:\\", "E:\\", "", "removable"),
        ],
        disk_usage=usage,
    )
    for name in ("sensors_temperatures", "sensors_fans"):  # psutil has none on Windows
        delattr(module, name)
    return module


async def test_windows_health_lists_drive_letters_and_skips_empty_drives() -> None:
    ps = windows_psutil()
    seen: list[str] = []
    real_usage = ps.disk_usage
    ps.disk_usage = lambda path: seen.append(path) or real_usage(path)
    text = await tools(ps)["system_health"].invoke(HealthArgs())
    assert "disk C:\\ 40.0% used" in text
    assert "D:" not in text and "E:" not in text
    assert seen == ["C:\\"]  # no drive without a file system is even asked


async def test_windows_has_no_temperature_sensors() -> None:
    text = await tools(windows_psutil())["system_temperatures"].invoke(TemperatureArgs())
    assert text == "No temperature sensors are readable here."
