"""The OS loader: one platform.system() check at boot picks one toolset, never both."""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

import zeno
from zeno.agent.tools import os_loader
from zeno.agent.tools.base import Risk
from zeno.config import Settings

TELEMETRY = {"system_health", "system_temperatures", "top_processes", "process_info"}
LINUX = TELEMETRY | {"notify_desktop", "service_status", "run_command"}
WINDOWS = TELEMETRY | {"notify_desktop", "service_status", "run_powershell"}
ZENO_DIR = Path(zeno.__file__).parent
BRAIN_DIR = ZENO_DIR.parent
has_dbus = importlib.util.find_spec("dbus_fast") is not None


def settings(tmp_path: Path, **values: object) -> Settings:
    return Settings(data_dir=tmp_path, run_command_roots=[tmp_path], **values)  # type: ignore[arg-type]


def names(toolset: os_loader.OsToolset) -> set[str]:
    return {t.name for t in toolset.tools}


@pytest.mark.parametrize(
    ("system", "expected"),
    [("Linux", "linux"), ("Windows", "windows"), ("Darwin", "other"), ("", "other")],
)
def test_host_os_reads_platform_system(system: str, expected: str) -> None:
    assert os_loader.host_os(lambda: system) == expected


def test_host_os_defaults_to_this_machine() -> None:
    expected = {"linux": "linux", "win32": "windows"}.get(sys.platform, "other")
    assert os_loader.host_os() == expected


@pytest.mark.parametrize("system", ["Linux", "Windows", "Darwin"])
def test_nothing_is_offered_until_turned_on(tmp_path: Path, system: str) -> None:
    toolset = os_loader.load_os_tools(settings(tmp_path), system=lambda: system)
    assert toolset.tools == [] and toolset.cleanups == []


@pytest.mark.skipif(not has_dbus, reason="dbus-fast is installed on Linux only")
def test_linux_gets_the_linux_toolset(tmp_path: Path) -> None:
    toolset = os_loader.load_os_tools(
        settings(tmp_path, os_tools=True, run_command=True), system=lambda: "Linux"
    )
    assert names(toolset) == LINUX
    assert len(toolset.cleanups) == 1  # the D-Bus connections


def test_windows_gets_the_windows_toolset(tmp_path: Path) -> None:
    toolset = os_loader.load_os_tools(
        settings(tmp_path, os_tools=True, run_command=True), system=lambda: "Windows"
    )
    assert names(toolset) == WINDOWS


@pytest.mark.parametrize("system", ["Linux", "Windows"])
def test_each_switch_is_independent(tmp_path: Path, system: str) -> None:
    if system == "Linux" and not has_dbus:
        pytest.skip("dbus-fast is installed on Linux only")
    only_os = os_loader.load_os_tools(settings(tmp_path, os_tools=True), system=lambda: system)
    assert "run_command" not in names(only_os) and "run_powershell" not in names(only_os)
    only_run = os_loader.load_os_tools(settings(tmp_path, run_command=True), system=lambda: system)
    (runner,) = only_run.tools
    assert runner.risk is Risk.PRIVILEGED


def test_other_systems_get_telemetry_only(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    toolset = os_loader.load_os_tools(
        settings(tmp_path, os_tools=True, run_command=True), system=lambda: "Darwin"
    )
    assert names(toolset) == TELEMETRY
    assert "Darwin" in caplog.text


def test_the_service_notifier_is_systemd_only_on_linux() -> None:
    linux = os_loader.service_notifier(lambda: "Linux")
    windows = os_loader.service_notifier(lambda: "Windows")
    assert type(linux).__name__ == "SystemdNotifier"
    assert type(windows).__name__ == "NullNotifier"
    assert windows.ready("x") is False and windows.watchdog_interval() is None


# --- isolation: Windows and Linux code never meet ------------------------------------

LINUX_SIDE = ("zeno.hostos.linux", "zeno.agent.tools.os_linux", "dbus_fast")
WINDOWS_SIDE = ("zeno.hostos.windows", "zeno.agent.tools.os_windows", "winrt")
LINUX_FILES = [
    "agent/tools/os_linux.py",
    *sorted(
        p.relative_to(ZENO_DIR).as_posix() for p in (ZENO_DIR / "hostos" / "linux").glob("*.py")
    ),
]
WINDOWS_FILES = [
    "agent/tools/os_windows.py",
    *sorted(
        p.relative_to(ZENO_DIR).as_posix() for p in (ZENO_DIR / "hostos" / "windows").glob("*.py")
    ),
]


def imported_modules(relative: str) -> set[str]:
    tree = ast.parse((ZENO_DIR / relative).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
    return found


@pytest.mark.parametrize("relative", LINUX_FILES)
def test_linux_code_never_imports_windows_code(relative: str) -> None:
    assert not {m for m in imported_modules(relative) if m.startswith(WINDOWS_SIDE)}


@pytest.mark.parametrize("relative", WINDOWS_FILES)
def test_windows_code_never_imports_linux_code(relative: str) -> None:
    assert not {m for m in imported_modules(relative) if m.startswith(LINUX_SIDE)}


def modules_loaded_for(system: str, tmp_path: Path) -> list[str]:
    script = f"""
import json, sys
from zeno.agent.tools import os_loader
from zeno.config import Settings
s = Settings(data_dir={str(tmp_path)!r}, os_tools=True, run_command=True,
             run_command_roots=[{str(tmp_path)!r}])
os_loader.load_os_tools(s, system=lambda: {system!r})
os_loader.service_notifier(lambda: {system!r})
print(json.dumps(sorted(sys.modules)))
"""
    done = subprocess.run(  # noqa: S603 - this interpreter, a fixed script
        [sys.executable, "-c", script], cwd=BRAIN_DIR, capture_output=True, text=True, check=True
    )
    loaded: list[str] = json.loads(done.stdout)
    return loaded


@pytest.mark.skipif(not has_dbus, reason="dbus-fast is installed on Linux only")
def test_booting_on_linux_loads_no_windows_module(tmp_path: Path) -> None:
    loaded = modules_loaded_for("Linux", tmp_path)
    assert "zeno.agent.tools.os_linux" in loaded
    assert not [m for m in loaded if m.startswith(WINDOWS_SIDE)]


def test_booting_on_windows_loads_no_linux_module(tmp_path: Path) -> None:
    loaded = modules_loaded_for("Windows", tmp_path)
    assert "zeno.agent.tools.os_windows" in loaded
    assert not [m for m in loaded if m.startswith(LINUX_SIDE)]
