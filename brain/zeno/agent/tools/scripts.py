"""The curated script runner: runs owner-approved Python files from one folder.

The model picks a script by name and passes plain string arguments. There is no
shell: the interpreter is started with an argument list, in the scripts folder,
with a small environment, a time limit and an output cap.
"""

import ast
import asyncio
import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, StringConstraints, field_validator

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool

ScriptName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
# Only what Python needs to start on each platform; the brain's own settings and
# any secrets in its environment are not passed on.
_ENV_KEYS = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG")


class ScriptListArgs(ToolArgs):
    pass


class RunScriptArgs(ToolArgs):
    name: ScriptName = Field(description="The script's name, without .py.")
    args: list[Annotated[str, StringConstraints(max_length=200)]] = Field(
        default_factory=list, max_length=10
    )

    @field_validator("args")
    @classmethod
    def _no_nul(cls, args: list[str]) -> list[str]:
        if any("\x00" in arg for arg in args):
            raise ValueError("arguments cannot contain NUL characters")
        return args


def script_tools(folder: Path, *, timeout: float, max_output: int) -> list[Tool[Any]]:
    @tool(risk=Risk.READ_ONLY, timeout=5.0)
    async def list_scripts(args: ScriptListArgs) -> str:
        """List the owner's scripts that can be run, with what each one does."""
        found = await asyncio.to_thread(_list, folder)
        if not found:
            return "No scripts are installed."
        return "\n".join(f"- {name}: {summary}" for name, summary in found)

    # Outlasts the script's own limit so the runner's clearer timeout is reported.
    @tool(risk=Risk.MUTATING, timeout=timeout + 2.0)
    async def run_script(args: RunScriptArgs) -> str:
        """Run one of the owner's scripts by name with optional text arguments."""
        path = _resolve(folder, args.name)
        code, output = await _run(path, args.args, timeout=timeout, max_output=max_output)
        return f"{args.name} finished with exit code {code}.\n{output}".rstrip()

    return [list_scripts, run_script]


def _list(folder: Path) -> list[tuple[str, str]]:
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.py")):
        try:
            doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
        except (OSError, SyntaxError, UnicodeDecodeError):
            doc = None
        found.append((path.stem, (doc or "No description.").splitlines()[0]))
    return found


def _resolve(folder: Path, name: str) -> Path:
    base = folder.resolve()
    path = folder / f"{name}.py"
    if not path.is_file():
        raise FileNotFoundError(f"There is no script called {name}.")
    resolved = path.resolve(strict=True)
    if resolved.parent != base:
        raise PermissionError(f"{name} points outside the scripts folder.")
    return resolved


async def _run(
    path: Path,
    args: list[str],
    *,
    timeout: float,  # noqa: ASYNC109  # the process must be killed on expiry, not just abandoned
    max_output: int,
) -> tuple[int, str]:
    env = {key: os.environ[key] for key in _ENV_KEYS if key in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",  # isolated: ignores PYTHON* variables and the user's site-packages
        str(path),
        *args,
        cwd=path.parent,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output = await asyncio.wait_for(_read_capped(process, max_output), timeout)
        code = await asyncio.wait_for(process.wait(), timeout)
    except BaseException:
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        raise
    return code, output


async def _read_capped(process: asyncio.subprocess.Process, limit: int) -> str:
    """Keep the first ``limit`` characters; drain (and drop) the rest so the
    script never blocks on a full pipe."""
    assert process.stdout is not None  # noqa: S101  # stdout=PIPE above
    kept = bytearray()
    dropped = 0
    while chunk := await process.stdout.read(65536):
        room = limit - len(kept)
        kept += chunk[:room]
        dropped += max(0, len(chunk) - room)
    text = kept.decode("utf-8", errors="replace")
    return f"{text}\n...[truncated {dropped} bytes]" if dropped else text
