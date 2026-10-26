"""ps_parse.ps1 through PowerShell's real parser. Skipped where no PowerShell is
installed; CI runs it on Windows (powershell and pwsh) and Ubuntu (pwsh)."""

import os
import shutil
from pathlib import Path

import pytest

from zeno.hostos.process import CommandRefused
from zeno.hostos.windows import powershell
from zeno.hostos.windows.ps_policy import PsContext, PsTree, check_powershell

EXE = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(EXE is None, reason="needs PowerShell")
CTX = PsContext(home="C:\\Users\\Boss", cwd="C:\\Users\\Boss\\projects", own_pid=4242)


async def parsed(text: str, cwd: Path) -> PsTree:
    assert EXE is not None
    return await powershell.parse_command(text, exe=EXE, cwd=str(cwd), env=dict(os.environ))


def nodes(tree: PsTree) -> list[tuple[str, dict[str, str]]]:
    found = []
    stack = [tree.root] if tree.root else []
    while stack:
        node = stack.pop()
        found.append((node.type, node.props))
        stack.extend(reversed(node.children))
    return found


async def test_the_tree_has_the_shape_the_policy_reads(tmp_path: Path) -> None:
    tree = await parsed("Get-Process | Sort-Object CPU -Descending", tmp_path)
    assert tree.errors == [] and tree.root is not None and tree.root.type == "ScriptBlockAst"
    found = nodes(tree)
    names = [props.get("CommandName") for kind, props in found if kind == "CommandAst"]
    assert names == ["Get-Process", "Sort-Object"]
    assert ("CommandParameterAst", "Descending") in [
        (kind, props.get("ParameterName")) for kind, props in found
    ]
    strings = [props for kind, props in found if kind == "StringConstantExpressionAst"]
    assert {"Value": "CPU", "StringConstantType": "BareWord"}.items() <= strings[-1].items()


async def test_the_alias_table_comes_along(tmp_path: Path) -> None:
    tree = await parsed("Get-Process", tmp_path)
    assert tree.aliases["iex"] == "Invoke-Expression"
    assert tree.aliases["%"] == "ForEach-Object"


async def test_parse_errors_are_reported(tmp_path: Path) -> None:
    tree = await parsed("Get-Process {", tmp_path)
    assert tree.errors


async def test_parsing_never_runs_the_command(tmp_path: Path) -> None:
    marker = tmp_path / "ran.txt"
    await parsed(f"New-Item -ItemType File -Path '{marker}'", tmp_path)
    await parsed(f"$(New-Item -ItemType File -Path '{marker}')", tmp_path)
    assert not marker.exists()


async def test_text_survives_the_round_trip(tmp_path: Path) -> None:
    tree = await parsed("Write-Output 'héllo ✓ \"quoted\"'", tmp_path)
    values = [
        props.get("Value") for kind, props in nodes(tree) if kind == "StringConstantExpressionAst"
    ]
    assert 'héllo ✓ "quoted"' in values


ALLOWED = [
    "Get-Process",
    "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5",
    "Get-Service | Where-Object { $_.Status -eq 'Running' }",
    "Get-Process | Where-Object { $PSItem.CPU -gt 10 } | ForEach-Object { $_.Name }",
    "Get-ChildItem -Recurse -Filter *.log",
    "Remove-Item .\\build -Recurse -Force",
    'Remove-Item "$HOME\\Desktop\\junk" -Recurse',
    "ipconfig /all",
    "Get-Content log.txt 2>&1",
    "Get-Process # Remove-Item C:\\ -Recurse",
]


@pytest.mark.parametrize("text", ALLOWED)
async def test_allowed_through_the_real_parser(text: str, tmp_path: Path) -> None:
    check_powershell(await parsed(text, tmp_path), CTX)


REFUSED = [
    "Remove-Item C:\\ -Recurse",
    "Remove-Item \u2013Recurse C:\\",  # an en dash works as a dash in PowerShell
    "rm -r C:\\Windows",
    "Remove-Item -Recurse -Path $HOME",
    "Remove-Item -Recurse -Path:C:\\Users",
    'Remove-Item "$env:USERPROFILE\\*" -Recurse',
    "Remove-Item C:\\Win* -Recurse",
    "Get-Process; Remove-Item x",
    "Get-Process &",
    "Get-Process && whoami",
    "& { Remove-Item x }",
    "& 'Remove-Item' x",
    ". .\\x.ps1",
    "iex 'calc'",
    "i`ex 'calc'",
    "Invoke-Expression ([char]105)",
    "[IO.File]::Delete('x')",
    "$x = 'iex'",
    "powershell -EncodedCommand AAAA",
    "cmd /c del x",
    "Start-Process notepad",
    "Get-Process | % Kill",
    "Get-Process | ForEach-Object { $_.Kill() }",
    "Get-ChildItem C:\\ | Remove-Item -Recurse",
    "Get-Process > out.txt",
    "Stop-Process -Name lsass",
    "Get-Item @args",
]


@pytest.mark.parametrize("text", REFUSED)
async def test_refused_through_the_real_parser(text: str, tmp_path: Path) -> None:
    with pytest.raises(CommandRefused):
        check_powershell(await parsed(text, tmp_path), CTX)
