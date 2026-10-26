"""The PowerShell policy: a pure check over PowerShell's own syntax tree, before approval.

``ps_parse.ps1`` asks PowerShell's real parser for the tree (it never runs the
command); ``parse_tree`` reads its JSON and ``check_powershell`` refuses, with a
reason, anything outside a small static subset of the language or in a fixed set
of dangerous commands:

- one pipeline, nothing in the background, no ``;``, ``&&`` or redirection to files;
- commands named literally (no ``&``, no ``.``, no computed names) and not ones that
  run other code (Invoke-Expression, Start-Process, cmd, python...);
- arguments that are literals, or ``$HOME`` / ``$env:USERPROFILE``; script blocks
  only for Where-Object, ForEach-Object, Sort-Object..., holding only comparisons of
  ``$_``'s properties: no commands and no method calls;
- no recursive delete of a protected folder (a drive root, anything one level below
  it, the home folder and its parents, Windows, Program Files), however it is spelled;
  no changes under HKLM; no disk, power, firewall, Defender or account commands; no
  stopping Windows' critical processes or Zeno itself.

What it does not refuse still needs the owner's approval: a denylist is a seatbelt,
not a judge. The command then runs in Constrained Language Mode (``os_windows``).
"""

import contextlib
import json
import ntpath
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from zeno.hostos.process import CommandRefused

__all__ = ["CommandRefused", "PsContext", "PsNode", "PsTree", "check_powershell", "parse_tree"]


@dataclass(eq=False)
class PsNode:
    type: str
    text: str
    props: dict[str, str]
    start: int
    children: list["PsNode"] = field(default_factory=list)
    parent: "PsNode | None" = None

    def prop(self, name: str) -> str:
        return self.props.get(name, "")


@dataclass(frozen=True)
class PsTree:
    root: PsNode | None
    errors: list[str]
    aliases: dict[str, str]
    """Lower-case alias name to the command it stands for."""


def _identity(path: str) -> str:
    return path


@dataclass(frozen=True)
class PsContext:
    home: str
    """The user's profile folder, e.g. C:\\Users\\Boss."""
    cwd: str
    own_pid: int
    system_root: str = "C:\\Windows"
    program_dirs: tuple[str, ...] = ("C:\\Program Files", "C:\\Program Files (x86)")
    realpath: Callable[[str], str] = _identity
    """Resolves junctions, links and short names; Windows' own on Windows."""


def parse_tree(raw: str) -> PsTree:
    """Read ps_parse.ps1's JSON. Anything unexpected is refused, never guessed at."""
    try:
        data = json.loads(raw)
        errors = [str(e) for e in data["errors"]]
        aliases = {str(k).lower(): str(v) for k, v in dict(data["aliases"]).items()}
        nodes: dict[int, PsNode] = {}
        parents: dict[int, int] = {}
        for item in data["nodes"]:
            index = int(item["id"])
            props = {str(k): str(v) for k, v in dict(item["props"]).items()}
            nodes[index] = PsNode(str(item["type"]), str(item["text"]), props, int(item["start"]))
            parents[index] = int(item["parent"])
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise CommandRefused(f"PowerShell's parser gave an unreadable answer ({error})") from error
    root = None
    for index, node in nodes.items():
        parent = parents[index]
        if parent == -1:
            if root is not None:
                raise CommandRefused("PowerShell's parser gave two roots")
            root = node
        elif parent in nodes:
            node.parent = nodes[parent]
            nodes[parent].children.append(node)
        else:
            raise CommandRefused("PowerShell's parser gave a node without its parent")
    for node in nodes.values():
        node.children.sort(key=lambda child: child.start)
    return PsTree(root, errors, aliases)


# --- what the language may contain ----------------------------------------------------

_ALLOWED = {
    "ScriptBlockAst",
    "NamedBlockAst",
    "PipelineAst",
    "CommandAst",
    "CommandExpressionAst",
    "CommandParameterAst",
    "StringConstantExpressionAst",
    "ConstantExpressionAst",
    "ExpandableStringExpressionAst",
    "ArrayLiteralAst",
    "VariableExpressionAst",
    "MergingRedirectionAst",  # 2>&1
    "ScriptBlockExpressionAst",
}
_ALLOWED_IN_BLOCKS = _ALLOWED - {"CommandAst"} | {
    "BinaryExpressionAst",
    "UnaryExpressionAst",
    "MemberExpressionAst",
    "ParenExpressionAst",
}
_HOME_VARIABLES = {"home", "env:userprofile"}
_VARIABLES = _HOME_VARIABLES | {"true", "false", "null"}
_BLOCK_VARIABLES = _VARIABLES | {"_", "psitem"}
_BLOCK_COMMANDS = {
    "where-object",
    "foreach-object",
    "sort-object",
    "select-object",
    "group-object",
    "measure-object",
}

# Built-in aliases that matter here, in case the parser's table lacks them (PowerShell
# on Linux has no rm or kill, for one). The parser's own table is read first.
_ALIASES = {
    "rm": "Remove-Item",
    "del": "Remove-Item",
    "erase": "Remove-Item",
    "rd": "Remove-Item",
    "rmdir": "Remove-Item",
    "ri": "Remove-Item",
    "rp": "Remove-ItemProperty",
    "sp": "Set-ItemProperty",
    "si": "Set-Item",
    "ni": "New-Item",
    "cli": "Clear-Item",
    "kill": "Stop-Process",
    "spps": "Stop-Process",
    "iex": "Invoke-Expression",
    "icm": "Invoke-Command",
    "saps": "Start-Process",
    "start": "Start-Process",
    "sajb": "Start-Job",
    "ii": "Invoke-Item",
    "ipmo": "Import-Module",
    "nsn": "New-PSSession",
    "etsn": "Enter-PSSession",
    "ihy": "Invoke-History",
    "r": "Invoke-History",
    "foreach": "ForEach-Object",
    "%": "ForEach-Object",
    "where": "Where-Object",
    "?": "Where-Object",
    "sort": "Sort-Object",
    "select": "Select-Object",
    "group": "Group-Object",
    "measure": "Measure-Object",
}
_MODULES = {
    "microsoft.powershell.core",
    "microsoft.powershell.management",
    "microsoft.powershell.utility",
    "microsoft.powershell.security",
}

# Commands that run other code, change who may do what, or can't be undone.
_REFUSED_CMDLETS = {
    "invoke-expression": "it runs text as code",
    "invoke-command": "it runs code",
    "start-process": "it starts other programs outside this check",
    "start-job": "it runs code in the background",
    "start-threadjob": "it runs code in the background",
    "invoke-item": "it opens or runs a file",
    "invoke-history": "it re-runs earlier commands",
    "add-type": "it compiles code",
    "invoke-wmimethod": "it runs WMI methods",
    "invoke-cimmethod": "it runs WMI methods",
    "new-pssession": "it opens remote sessions",
    "enter-pssession": "it opens remote sessions",
    "import-module": "it loads code",
    "install-module": "it installs code",
    "install-package": "it installs code",
    "set-executionpolicy": "it weakens script protection",
    "register-scheduledtask": "it schedules code to run later",
    "set-scheduledtask": "it changes scheduled code",
    "new-service": "it installs a service",
    "format-volume": "it erases a disk",
    "clear-disk": "it erases a disk",
    "initialize-disk": "it erases a disk",
    "remove-partition": "it destroys a partition",
    "set-partition": "it changes a partition",
    "resize-partition": "it changes a partition",
    "stop-computer": "it turns the computer off",
    "restart-computer": "it restarts the computer",
    "suspend-bitlocker": "it weakens disk encryption",
    "disable-bitlocker": "it removes disk encryption",
    "set-netfirewallprofile": "it changes the firewall",
    "new-localuser": "it changes user accounts",
    "remove-localuser": "it changes user accounts",
    "set-localuser": "it changes user accounts",
    "add-localgroupmember": "it changes user accounts",
    "remove-localgroupmember": "it changes user accounts",
    "set-acl": "it changes file permissions",
}
_REFUSED_PROGRAMS = {
    **dict.fromkeys(
        [
            "cmd",
            "powershell",
            "powershell_ise",
            "pwsh",
            "wscript",
            "cscript",
            "mshta",
            "rundll32",
            "regsvr32",
            "msiexec",
            "wsl",
            "bash",
            "sh",
            "python",
            "python3",
            "py",
            "pyw",
            "pythonw",
            "node",
            "java",
            "javaw",
            "perl",
            "ruby",
            "php",
            "wmic",
            "certutil",
            "bitsadmin",
            "forfiles",
            "runas",
            "msbuild",
            "installutil",
            "regasm",
            "regsvcs",
            "csc",
            "cmstp",
            "odbcconf",
            "mavinject",
            "hh",
            "pcalua",
            "msdt",
            "explorer",
            "control",
            "regedit",
            "at",
            "psexec",
        ],
        "it runs other code",
    ),
    "diskpart": "it can erase disks",
    "format": "it erases a disk",
    "bcdedit": "it changes how Windows boots",
    "bcdboot": "it changes how Windows boots",
    "takeown": "it changes file ownership",
    "icacls": "it changes file permissions",
    "cacls": "it changes file permissions",
    "shutdown": "it turns the computer off",
}
_SCRIPT_FILE = re.compile(
    r"\.(ps1|psm1|psd1|bat|cmd|vbs|vbe|js|jse|wsf|wsh|hta|lnk|msi|msc|cpl|scr|reg)$", re.I
)
_PROGRAM_EXT = re.compile(r"\.(exe|com)$", re.I)
_CRITICAL = {"csrss", "wininit", "winlogon", "lsass", "services", "smss", "svchost", "system"}
_REGISTRY = re.compile(
    r"^(registry::)?(hklm|hkcr|hku|hkey_local_machine|hkey_classes_root|hkey_users)\b", re.I
)
_OTHER_PROVIDER = re.compile(r"^(cert|wsman):", re.I)
_REGISTRY_CMDLETS = {
    "remove-item",
    "remove-itemproperty",
    "set-itemproperty",
    "new-itemproperty",
    "set-item",
    "new-item",
    "clear-item",
    "clear-itemproperty",
    "rename-item",
    "rename-itemproperty",
    "move-item",
    "copy-item",
}
# Commands that must name what they act on: fed from a pipeline, the targets are unknown.
_EXPLICIT_TARGETS = {"remove-item", "remove-itemproperty", "stop-process", "clear-item"}
# Parameters whose value is never a path to delete.
_NOT_PATHS = ("filter", "include", "exclude", "stream", "credential", "erroraction")


@dataclass
class _Arg:
    param: str | None
    value: PsNode


def check_powershell(tree: PsTree, ctx: PsContext) -> None:
    """Return quietly if the command may go to the owner; else raise ``CommandRefused``."""
    if tree.errors:
        raise CommandRefused(f"PowerShell can't parse it: {tree.errors[0]}")
    root = tree.root
    if root is None or root.type != "ScriptBlockAst":
        raise CommandRefused("PowerShell's parser found no command")
    blocks = root.children
    if len(blocks) != 1 or blocks[0].type != "NamedBlockAst" or len(blocks[0].children) != 1:
        raise CommandRefused("give exactly one command (no ; and no begin/process blocks)")
    statement = blocks[0].children[0]
    if statement.type != "PipelineAst":
        raise CommandRefused(f"{statement.type} is not allowed here; give one command")
    for node in _walk(root):
        _check_node(node, tree, ctx)


def _walk(node: PsNode) -> Iterator[PsNode]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _in_block(node: PsNode) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.type == "ScriptBlockExpressionAst":
            return True
        parent = parent.parent
    return False


def _check_node(node: PsNode, tree: PsTree, ctx: PsContext) -> None:
    inside = _in_block(node)
    allowed = _ALLOWED_IN_BLOCKS if inside else _ALLOWED
    if node.type not in allowed:
        if node.type == "CommandAst":
            raise CommandRefused("commands inside a script block are not allowed")
        raise CommandRefused(f"{node.type} is not allowed here ({node.text[:60]!r})")
    if node.type == "PipelineAst" and node.prop("Background") == "True":
        raise CommandRefused("running a command in the background (&) is not allowed")
    if node.type == "VariableExpressionAst":
        name = node.prop("VariablePath").lower()
        if node.prop("Splatted") == "True":
            raise CommandRefused("splatting (@name) is not allowed")
        if name not in (_BLOCK_VARIABLES if inside else _VARIABLES):
            raise CommandRefused(
                f"the variable ${node.prop('VariablePath')} is not allowed; write the value"
            )
    if node.type == "MemberExpressionAst" and node.prop("Static") != "False":
        raise CommandRefused("static members are not allowed")
    if node.type == "ScriptBlockExpressionAst":
        owner = node.parent
        if (
            owner is None
            or owner.type != "CommandAst"
            or _command(owner, tree)[0] not in (_BLOCK_COMMANDS)
        ):
            raise CommandRefused(
                "a script block is only allowed as the filter of Where-Object, "
                "ForEach-Object, Sort-Object, Select-Object, Group-Object or Measure-Object"
            )
    if node.type == "CommandAst":
        _check_command(node, tree, ctx)


def _command(node: PsNode, tree: PsTree) -> tuple[str, bool]:
    """The command's canonical lower-case name, and whether it is a program file."""
    operator = node.prop("InvocationOperator")
    if operator == "Ampersand":
        raise CommandRefused("the & call operator is not allowed; name the command directly")
    if operator == "Dot":
        raise CommandRefused("dot-sourcing (. script) is not allowed")
    name = node.props.get("CommandName")
    if not name or not node.children or node.children[0].type != "StringConstantExpressionAst":
        raise CommandRefused("a command whose name is computed is not allowed")
    lowered = name.lower()
    if lowered in tree.aliases:
        return tree.aliases[lowered].lower(), False
    if lowered in _ALIASES:
        return _ALIASES[lowered].lower(), False
    module, sep, rest = lowered.partition("\\")
    if sep and module in _MODULES and "\\" not in rest:
        return rest, False
    if "\\" in name or "/" in name or ":" in name:
        return name, True
    return lowered, _PROGRAM_EXT.search(lowered) is not None


def _check_command(node: PsNode, tree: PsTree, ctx: PsContext) -> None:
    name, is_file = _command(node, tree)
    if _SCRIPT_FILE.search(name):
        raise CommandRefused(f"running a script file ({name}) is not allowed")
    if is_file and ("\\" in name or "/" in name or ":" in name):
        resolved = _normalize(name, ctx)
        if not _within(resolved, _normalize(ctx.system_root, ctx)):
            raise CommandRefused(
                f"{name}: only programs from Windows' own folders (or found on PATH) may run"
            )
        name = ntpath.basename(resolved)
    program = _PROGRAM_EXT.sub("", name.lower())
    args = _arguments(node)
    position = _pipeline_position(node)
    if program in _REFUSED_CMDLETS:
        raise CommandRefused(f"{_title(program)} is not allowed: {_REFUSED_CMDLETS[program]}")
    if program in _REFUSED_PROGRAMS:
        raise CommandRefused(f"{program} is not allowed: {_REFUSED_PROGRAMS[program]}")
    if program in _EXPLICIT_TARGETS and position > 0:
        raise CommandRefused(
            f"{_title(program)} must name its targets, not take them from a pipeline"
        )
    rule = _RULES.get(program)
    if rule is not None:
        rule(program, args, ctx)
    if program in _REGISTRY_CMDLETS:
        for arg in args:
            text = _static(arg.value, ctx)
            if text is not None and _REGISTRY.match(text):
                raise CommandRefused(f"{_title(program)} may not change the machine registry")
    if program == "remove-item":
        for arg in args:
            text = _static(arg.value, ctx)
            if text is not None and _OTHER_PROVIDER.match(text):
                raise CommandRefused("Remove-Item may not remove certificates or WSMan settings")


def _title(lowered: str) -> str:
    return "-".join(part.capitalize() for part in lowered.split("-"))


def _pipeline_position(node: PsNode) -> int:
    parent = node.parent
    if parent is None or parent.type != "PipelineAst":
        return 0
    return parent.children.index(node)


def _arguments(node: PsNode) -> list[_Arg]:
    """Each value, with the parameter it most likely follows (or None)."""
    args: list[_Arg] = []
    last: str | None = None
    for element in node.children[1:]:
        if element.type == "CommandParameterAst":
            last = element.prop("ParameterName").lower()
            args.append(_Arg(last, element))  # the parameter itself, valueless
            for inline in element.children:  # -Path:C:\
                args.append(_Arg(last, inline))
            continue
        if element.type == "MergingRedirectionAst":
            continue
        args.append(_Arg(last, element))
        last = None
    return args


def _values(args: list[_Arg]) -> list[_Arg]:
    return [a for a in args if a.value.type != "CommandParameterAst"]


def _params(args: list[_Arg]) -> list[str]:
    return [
        a.value.prop("ParameterName").lower() for a in args if a.value.type == "CommandParameterAst"
    ]


def _static(node: PsNode, ctx: PsContext) -> str | None:
    """A value known before running, with $HOME filled in; None when it is computed."""
    if node.type in ("StringConstantExpressionAst", "ConstantExpressionAst"):
        return node.prop("Value")
    if node.type == "VariableExpressionAst":
        return ctx.home if node.prop("VariablePath").lower() in _HOME_VARIABLES else None
    if node.type == "ExpandableStringExpressionAst":
        if any(
            c.type != "VariableExpressionAst"
            or c.prop("VariablePath").lower() not in _HOME_VARIABLES
            for c in node.children
        ):
            return None
        text = re.sub(
            r"\$\{?(home|env:userprofile)\}?", lambda _: ctx.home, node.prop("Value"), flags=re.I
        )
        return None if "$" in text else text
    return None


def _flat(args: list[_Arg]) -> Iterator[tuple[str | None, PsNode]]:
    for arg in _values(args):
        if arg.value.type == "ArrayLiteralAst":
            for item in arg.value.children:
                yield arg.param, item
        else:
            yield arg.param, arg.value


def _matches(param: str, *names: str) -> bool:
    """PowerShell takes any unambiguous prefix; count any prefix (fail closed)."""
    return any(name.startswith(param) for name in names) if param else False


# --- per-command rules ----------------------------------------------------------------


def _remove_item(name: str, args: list[_Arg], ctx: PsContext) -> None:
    recursive = any(_matches(p, "recurse") for p in _params(args)) or any(
        (_static(v, ctx) or "").lower() == "/s" for _, v in _flat(args)
    )
    if not recursive:
        return
    for param, value in _flat(args):
        if param is not None and any(_matches(param, n) for n in _NOT_PATHS):
            continue
        text = _static(value, ctx)
        if text is None:
            raise CommandRefused(
                f"Remove-Item -Recurse with a computed path ({value.text[:40]}) can't be checked"
            )
        if text.lower() in ("/s", "/q"):
            continue
        reason = _protected(text, ctx)
        if reason:
            raise CommandRefused(f"Remove-Item -Recurse on {text} is refused: {reason}")


def _stop_process(name: str, args: list[_Arg], ctx: PsContext) -> None:
    for _, value in _flat(args):
        text = _static(value, ctx)
        if text is None:
            raise CommandRefused("Stop-Process with a computed target can't be checked")
        _check_process_target(text, ctx)


def _check_process_target(text: str, ctx: PsContext) -> None:
    if text.isdigit():
        pid = int(text)
        if pid == ctx.own_pid:
            raise CommandRefused("stopping Zeno's own process is not allowed")
        if pid in (0, 4):
            raise CommandRefused(f"process {pid} is part of Windows itself")
        return
    if any(c in text for c in "*?["):
        raise CommandRefused(f"stopping processes by wildcard ({text}) is not allowed")
    base = _PROGRAM_EXT.sub("", text.lower())
    if base in _CRITICAL:
        raise CommandRefused(f"{text} is a critical Windows process")


def _taskkill(name: str, args: list[_Arg], ctx: PsContext) -> None:
    texts = [(_static(v, ctx) or "") for _, v in _flat(args)]
    for index, text in enumerate(texts):
        flag = text.lower()
        if flag in ("/fi", "-fi"):
            raise CommandRefused("taskkill with a filter (/fi) is not allowed; name the process")
        if flag in ("/im", "-im", "/pid", "-pid") and index + 1 < len(texts):
            _check_process_target(texts[index + 1], ctx)
        if "*" in text:
            raise CommandRefused("taskkill with a wildcard is not allowed")


def _set_mp(name: str, args: list[_Arg], ctx: PsContext) -> None:
    for param in _params(args):
        if param.startswith("disable") or "disable".startswith(param[:7]):
            raise CommandRefused("turning Defender protection off is not allowed")
        if name == "add-mppreference" and (
            param.startswith("exclusion") or "exclusion".startswith(param[:9])
        ):
            raise CommandRefused("adding Defender exclusions is not allowed")


def _new_object(name: str, args: list[_Arg], ctx: PsContext) -> None:
    if any(_matches(p, "comobject") for p in _params(args)):
        raise CommandRefused("New-Object -ComObject is not allowed: COM objects can run code")


def _foreach(name: str, args: list[_Arg], ctx: PsContext) -> None:
    if any(_matches(p, "membername", "argumentlist") for p in _params(args)) or any(
        value.type != "ScriptBlockExpressionAst" for _, value in _flat(args)
    ):
        raise CommandRefused(
            "ForEach-Object only takes a script block here (its member form can call methods)"
        )


def _words(args: list[_Arg], ctx: PsContext) -> list[str]:
    return [(_static(v, ctx) or "\x00").lower() for _, v in _flat(args)]


def _native_rule(
    check: Callable[[list[str]], str | None],
) -> Callable[[str, list[_Arg], PsContext], None]:
    def rule(name: str, args: list[_Arg], ctx: PsContext) -> None:
        reason = check(_words(args, ctx))
        if reason:
            raise CommandRefused(f"{name} {reason}")

    return rule


def _cipher(words: list[str]) -> str | None:
    return (
        "/w wipes free space and is not allowed" if any(w.startswith("/w") for w in words) else None
    )


def _net(words: list[str]) -> str | None:
    if words and words[0] in ("user", "localgroup", "group", "accounts"):
        return "may not change user accounts"
    return None


def _reg(words: list[str]) -> str | None:
    if words and words[0] in ("delete", "add", "import", "restore", "load", "unload", "copy"):
        keys = words[1:2]
        if not keys or not keys[0].startswith(("hkcu", "hkey_current_user")):
            return f"{words[0]} may only change your own registry (HKCU)"
    return None


_RULES: dict[str, Callable[[str, list[_Arg], PsContext], None]] = {
    "remove-item": _remove_item,
    "stop-process": _stop_process,
    "taskkill": _taskkill,
    "set-mppreference": _set_mp,
    "add-mppreference": _set_mp,
    "new-object": _new_object,
    "foreach-object": _foreach,
    "cipher": _native_rule(_cipher),
    "vssadmin": _native_rule(
        lambda w: (
            "may not delete or resize shadow copies" if {"delete", "resize"} & set(w) else None
        )
    ),
    "wbadmin": _native_rule(lambda w: "may not delete backups" if "delete" in w else None),
    "net": _native_rule(_net),
    "net1": _native_rule(_net),
    "netsh": _native_rule(
        lambda w: "may not change the firewall" if {"advfirewall", "firewall"} & set(w) else None
    ),
    "reg": _native_rule(_reg),
    "schtasks": _native_rule(
        lambda w: (
            "may only list tasks"
            if {"/create", "/change", "/run", "/delete", "/end"} & set(w)
            else None
        )
    ),
    "sc": _native_rule(
        lambda w: (
            "may not create, reconfigure or delete services"
            if {"create", "config", "delete", "failure", "sdset", "privs", "sidtype", "triggerinfo"}
            & set(w)
            else None
        )
    ),
}


# --- protected paths ------------------------------------------------------------------

_SHORT_NAME = re.compile(r"~\d")


def _normalize(raw: str, ctx: PsContext) -> str:
    """An absolute Windows path, as Windows itself would read it (case kept)."""
    path = raw.replace("/", "\\")
    if "::" in path:  # Microsoft.PowerShell.Core\FileSystem::C:\x
        path = path.rsplit("::", 1)[1]
    for prefix in ("\\\\?\\unc\\", "\\\\.\\unc\\"):
        if path.lower().startswith(prefix):
            path = "\\\\" + path[len(prefix) :]
    for prefix in ("\\\\?\\", "\\\\.\\"):
        if path.startswith(prefix):
            path = path[len(prefix) :]
    if path == "~" or path.startswith("~\\"):
        path = ctx.home + path[1:]
    drive, rest = ntpath.splitdrive(path)
    if drive and len(drive) == 2 and not rest.startswith("\\"):
        path = drive + "\\" + rest  # C:foo is relative to C:'s current folder: assume its root
    elif not drive and path.startswith("\\") and not path.startswith("\\\\"):
        path = ntpath.splitdrive(ctx.cwd)[0] + path
    elif not drive:
        path = ntpath.join(ctx.cwd, path)
    drive, rest = ntpath.splitdrive(path)
    parts = []
    for part in rest.split("\\"):
        if part in ("", ".", ".."):
            parts.append(part)
        else:  # Windows drops trailing dots and spaces: "Windows." is "Windows"
            parts.append(part.rstrip(" .") or ".")
    return ntpath.normpath(drive + "\\".join(parts))


def _within(path: str, root: str) -> bool:
    path, root = path.lower(), root.lower()
    return path == root or path.startswith(root.rstrip("\\") + "\\")


def _protected(raw: str, ctx: PsContext) -> str | None:
    lexical = _normalize(raw, ctx)
    wild = re.search(r"[*?\[]", lexical)
    if wild:  # C:\Users\Boss\* removes the home folder's contents: judge its parent
        lexical = lexical[: wild.start()].rsplit("\\", 1)[0] or lexical[:2]
        if lexical.endswith(":"):
            lexical += "\\"
    if _SHORT_NAME.search(lexical):
        return "it uses a short (8.3) name that can't be checked; write the full name"
    candidates = {lexical}
    with contextlib.suppress(OSError):
        candidates.add(_normalize(ctx.realpath(lexical), ctx))
    for path in candidates:
        reason = _protected_path(path, ctx)
        if reason:
            return reason
    return None


def _protected_path(path: str, ctx: PsContext) -> str | None:
    _, rest = ntpath.splitdrive(path)
    depth = len([part for part in rest.split("\\") if part])
    if depth <= 1:
        return "it is a drive, share or top-level folder (protected)"
    home = _normalize(ctx.home, ctx)
    if _within(home, path):
        return "it is your home folder or holds it (protected)"
    for system in (ctx.system_root, *ctx.program_dirs):
        if _within(path, _normalize(system, ctx)):
            return f"it is inside {system} (protected)"
    return None
