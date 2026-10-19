"""The curated script runner: only files in the scripts folder, run without a shell."""

import os
import sys
import time
from pathlib import Path

import pytest

from zeno.agent.tools.base import Risk, Tool
from zeno.agent.tools.scripts import RunScriptArgs, ScriptListArgs, script_tools

ECHO = """import sys
print("args:", sys.argv[1:])
print("cwd:", __import__("os").getcwd())
"""


def write(folder: Path, name: str, body: str) -> Path:
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def scripts(tmp_path: Path) -> Path:
    folder = (tmp_path / "scripts").resolve()
    folder.mkdir()
    write(folder, "echo.py", '"""Print the arguments back."""\n' + ECHO)
    write(folder, "fail.py", "import sys\nprint('broken')\nsys.exit(3)\n")
    write(folder, "slow.py", "import time\ntime.sleep(30)\n")
    write(folder, "chatty.py", "print('x' * 100000)\n")
    write(folder, "notes.txt", "not a script")
    return folder


def tools(folder: Path, *, timeout: float = 5.0, max_output: int = 2000) -> dict[str, Tool]:  # type: ignore[type-arg]
    return {t.name: t for t in script_tools(folder, timeout=timeout, max_output=max_output)}


async def test_lists_only_python_scripts_with_their_summary(scripts: Path) -> None:
    text = await tools(scripts)["list_scripts"].invoke(ScriptListArgs())
    assert "echo: Print the arguments back." in text
    assert "fail" in text and "slow" in text
    assert "notes" not in text


async def test_runs_a_script_with_arguments_in_its_folder(scripts: Path) -> None:
    text = await tools(scripts)["run_script"].invoke(
        RunScriptArgs(name="echo", args=["one", "two words", "$(rm -rf ~)"])
    )
    assert "exit code 0" in text
    # Arguments arrive verbatim: no shell ever sees them.
    assert "['one', 'two words', '$(rm -rf ~)']" in text
    assert f"cwd: {scripts}" in text


async def test_reports_a_failing_exit_code(scripts: Path) -> None:
    text = await tools(scripts)["run_script"].invoke(RunScriptArgs(name="fail"))
    assert "exit code 3" in text and "broken" in text


async def test_kills_a_script_that_runs_too_long(scripts: Path) -> None:
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await tools(scripts, timeout=0.5)["run_script"].invoke(RunScriptArgs(name="slow"))
    assert time.monotonic() - started < 5


async def test_caps_the_output(scripts: Path) -> None:
    text = await tools(scripts, max_output=500)["run_script"].invoke(RunScriptArgs(name="chatty"))
    assert len(text) < 700
    assert "truncated" in text


async def test_unknown_scripts_are_refused(scripts: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await tools(scripts)["run_script"].invoke(RunScriptArgs(name="missing"))
    with pytest.raises(FileNotFoundError):
        await tools(scripts)["run_script"].invoke(RunScriptArgs(name="notes"))


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin rights on Windows")
async def test_a_symlink_out_of_the_folder_is_refused(scripts: Path, tmp_path: Path) -> None:
    outside = write(tmp_path, "evil.py", "print('escaped')\n")
    os.symlink(outside, scripts / "evil.py")
    with pytest.raises(PermissionError):
        await tools(scripts)["run_script"].invoke(RunScriptArgs(name="evil"))


@pytest.mark.parametrize(
    "name", ["../evil", "/etc/passwd", "echo.py", "Echo", "a b", "", "x" * 65, "echo;ls"]
)
def test_script_names_are_validated(name: str) -> None:
    with pytest.raises(ValueError):
        RunScriptArgs(name=name)


@pytest.mark.parametrize("args", [["a\x00b"], ["x" * 201], ["a"] * 11])
def test_script_arguments_are_validated(args: list[str]) -> None:
    with pytest.raises(ValueError):
        RunScriptArgs(name="echo", args=args)


def test_running_a_script_needs_approval(scripts: Path) -> None:
    found = tools(scripts)
    assert found["run_script"].risk is Risk.MUTATING
    assert found["list_scripts"].risk is Risk.READ_ONLY


def test_tool_timeout_outlasts_the_script_timeout(scripts: Path) -> None:
    assert tools(scripts, timeout=7.0)["run_script"].timeout > 7.0


async def test_a_missing_folder_lists_nothing(tmp_path: Path) -> None:
    text = await tools(tmp_path / "nope")["list_scripts"].invoke(ScriptListArgs())
    assert "No scripts" in text
