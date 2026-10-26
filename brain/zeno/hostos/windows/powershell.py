"""Find PowerShell, ask its parser about a command, and build the command line that runs
an approved one in Constrained Language Mode."""

import base64
import ntpath
import re
from collections.abc import Callable
from pathlib import Path

from zeno.hostos.process import CommandRefused, Runner
from zeno.hostos.windows.process import run_windows_process
from zeno.hostos.windows.ps_policy import PsTree, parse_tree

HELPER = Path(__file__).with_name("ps_parse.ps1")
PARSE_SECONDS = 12.0
PARSE_MAX_OUTPUT = 4_000_000
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# Runs before the approved command, in the same session. The last line is one-way:
# from then on no .NET method calls, Add-Type or COM.
PREAMBLE = (
    "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
    "$ProgressPreference = 'SilentlyContinue'\n"
    "$ExecutionContext.SessionState.LanguageMode = 'ConstrainedLanguage'\n"
)
FLAGS = ("-NoLogo", "-NoProfile", "-NonInteractive")


def find_powershell(
    system_root: str,
    program_dirs: tuple[str, ...],
    *,
    exists: Callable[[str], bool],
) -> str:
    """PowerShell 7 when installed in Program Files, else Windows PowerShell 5.1."""
    for folder in program_dirs:
        candidate = ntpath.join(folder, "PowerShell", "7", "pwsh.exe")
        if exists(candidate):
            return candidate
    return ntpath.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def run_argv(exe: str, command: str) -> list[str]:
    """The command line for an approved command: no profile, no .ps1 files, constrained."""
    encoded = base64.b64encode((PREAMBLE + command).encode("utf-16-le")).decode("ascii")
    return [exe, *FLAGS, "-ExecutionPolicy", "Restricted", "-EncodedCommand", encoded]


def parse_argv(exe: str, command: str) -> list[str]:
    encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
    return [exe, *FLAGS, "-ExecutionPolicy", "Bypass", "-File", str(HELPER), encoded]


async def parse_command(
    command: str, *, exe: str, cwd: str, env: dict[str, str], runner: Runner | None = None
) -> PsTree:
    """PowerShell's own syntax tree for the command. Parsing never runs it."""
    run = runner or run_windows_process
    result = await run(
        parse_argv(exe, command),
        cwd=cwd,
        seconds=PARSE_SECONDS,
        env=env,
        max_output=PARSE_MAX_OUTPUT,
    )
    if result.killed or result.exit_code != 0:
        detail = " ".join(ANSI.sub("", result.stderr).split()) or "no detail"
        raise CommandRefused(f"PowerShell's parser could not read it ({detail[:200]})")
    return parse_tree(result.stdout)
