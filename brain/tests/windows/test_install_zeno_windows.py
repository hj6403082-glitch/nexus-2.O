"""daemons/install_zeno_windows.ps1: the J.A.R.V.I.S. installer, never elevated."""

import os
import re
import shutil
from pathlib import Path

import pytest

from zeno.hostos.windows import powershell
from zeno.hostos.windows.toast import APP_ID

SCRIPT = Path(__file__).parents[2] / "daemons" / "install_zeno_windows.ps1"
TEXT = SCRIPT.read_text(encoding="utf-8")
EXE = os.environ.get("ZENO_TEST_POWERSHELL") or shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.parametrize(
    "needed",
    [
        r"New-ScheduledTaskTrigger -AtLogOn -User \$User",
        r"-RunLevel Limited",
        r"-LogonType Interactive",
        r"-RestartCount 999",
        r"\.venv\\Scripts\\pythonw\.exe",
        r"-Argument '-m zeno serve' -WorkingDirectory \$Brain",
        r"shell_integration --install",
        r"shell_integration --remove",
        r"\[switch\]\$Remove",
    ],
)
def test_the_installer_registers_the_logon_task_and_menu(needed: str) -> None:
    assert re.search(needed, TEXT), needed


def test_it_never_asks_for_admin() -> None:
    # The daemon runs as the user; the whole point of the per-command UAC decision.
    assert "RunLevel Highest" not in TEXT
    assert "-Verb RunAs" not in TEXT
    assert "HKLM:" not in TEXT


def test_the_toast_identity_matches_the_toaster() -> None:
    assert f"$AppId = '{APP_ID}'" in TEXT


def test_logs_go_where_the_brain_writes_them() -> None:
    from zeno.config import Settings

    assert Settings().log_file == Path("data/logs/zeno.log")
    assert "data\\logs\\zeno.log" in TEXT


@pytest.mark.skipif(EXE is None, reason="needs PowerShell")
async def test_powershell_parses_the_script(tmp_path: Path) -> None:
    assert EXE is not None
    tree = await powershell.parse_command(TEXT, exe=EXE, cwd=str(tmp_path), env=dict(os.environ))
    assert tree.errors == []
