"""The PowerShell policy: a pure check over PowerShell's own syntax tree, before approval.

Trees are built with tests/windows/ps_trees.py, so these run on any OS."""

import ntpath

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.windows.ps_trees import (
    N,
    arr,
    binop,
    block,
    call,
    cmd,
    dump,
    expr,
    member,
    num,
    one,
    other,
    p,
    pipe,
    q,
    s,
    script,
    var,
    xs,
)
from zeno.hostos.process import CommandRefused
from zeno.hostos.windows.ps_policy import PsContext, check_powershell, parse_tree

HOME = "C:\\Users\\Boss"
CTX = PsContext(home=HOME, cwd=HOME + "\\projects", own_pid=4242)


def check(root: N, ctx: PsContext = CTX, **extra: object) -> None:
    check_powershell(parse_tree(dump(root, **extra)), ctx)  # type: ignore[arg-type]


def refused(root: N, ctx: PsContext = CTX, **extra: object) -> str:
    with pytest.raises(CommandRefused) as caught:
        check(root, ctx, **extra)
    return str(caught.value)


# --- what is allowed (it still needs the owner's approval) ----------------------------

ALLOWED = {
    "Get-Process": one(cmd("Get-Process")),
    "Get-ChildItem -Recurse -Filter *.log": one(
        cmd("Get-ChildItem", p("Recurse"), p("Filter"), s("*.log"))
    ),
    "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5": one(
        cmd("Get-Process"),
        cmd("Sort-Object", s("CPU"), p("Descending")),
        cmd("Select-Object", p("First"), num(5)),
    ),
    "Get-Service | Where-Object { $_.Status -eq 'Running' }": one(
        cmd("Get-Service"),
        cmd(
            "Where-Object",
            block(pipe(expr(binop(member(var("_"), "Status"), "Ieq", q("Running"))))),
        ),
    ),
    "gps | ? { $PSItem.CPU -gt 10 } | % { $_.Name }": one(
        cmd("gps"),
        cmd("?", block(pipe(expr(binop(member(var("PSItem"), "CPU"), "Igt", num(10)))))),
        cmd("%", block(pipe(expr(member(var("_"), "Name"))))),
    ),
    "Remove-Item .\\build -Recurse -Force": one(
        cmd("Remove-Item", s(".\\build"), p("Recurse"), p("Force"))
    ),
    "Remove-Item ~\\projects\\old\\* -Recurse": one(
        cmd("Remove-Item", s("~\\projects\\old\\*"), p("Recurse"))
    ),
    "Remove-Item C:\\Users\\Boss\\Downloads\\x.zip": one(
        cmd("Remove-Item", s("C:\\Users\\Boss\\Downloads\\x.zip"))
    ),
    "Remove-Item $HOME\\Desktop\\junk -Recurse": one(
        cmd("Remove-Item", xs("$HOME\\Desktop\\junk", var("HOME")), p("Recurse"))
    ),
    "Get-ChildItem *.tmp | Remove-Item": None,  # filled below: refused, see the next section
    "Stop-Process -Name notepad": one(cmd("Stop-Process", p("Name"), s("notepad"))),
    "Stop-Process -Id 1234": one(cmd("Stop-Process", p("Id"), num(1234))),
    "ipconfig /all": one(cmd("ipconfig", s("/all"))),
    "C:\\Windows\\System32\\ipconfig.exe": one(cmd("C:\\Windows\\System32\\ipconfig.exe")),
    "Get-Content log.txt 2>&1": one(
        cmd("Get-Content", s("log.txt"), other("MergingRedirectionAst", FromStream="Error"))
    ),
    "Restart-Service Spooler": one(cmd("Restart-Service", s("Spooler"))),
    "reg query HKLM\\Software": one(cmd("reg", s("query"), s("HKLM\\Software"))),
    "reg add HKCU\\Software\\Zeno /v x /d 1": one(
        cmd("reg", s("add"), s("HKCU\\Software\\Zeno"), s("/v"), s("x"), s("/d"), num(1))
    ),
    "sc.exe query Spooler": one(cmd("sc.exe", s("query"), s("Spooler"))),
    "netsh interface show interface": one(cmd("netsh", s("interface"), s("show"), s("interface"))),
    "New-Object System.Text.StringBuilder": one(cmd("New-Object", s("System.Text.StringBuilder"))),
    "Microsoft.PowerShell.Management\\Get-Process": one(
        cmd("Microsoft.PowerShell.Management\\Get-Process")
    ),
    "Get-Item 'a','b'": one(cmd("Get-Item", arr(q("a"), q("b")))),
}
ALLOWED = {k: v for k, v in ALLOWED.items() if v is not None}


@pytest.mark.parametrize("text", ALLOWED)
def test_allowed(text: str) -> None:
    check(ALLOWED[text])


# --- refused before the owner is asked ------------------------------------------------

REFUSED: dict[str, tuple[N, str]] = {
    # the parser said no
    "parse error": (one(cmd("Get-Process")), "parse"),
    # more than one thing, or something in the background
    "a; b": (script(pipe(cmd("Get-Process")), pipe(cmd("Get-Service"))), "one command"),
    "a &": (script(pipe(cmd("Get-Process"), background=True)), "background"),
    "a && b": (
        script(other("PipelineChainAst", pipe(cmd("a")), pipe(cmd("b")))),
        "PipelineChainAst",
    ),
    # code that runs other code
    "& $x": (one(cmd(var("x"), op="Ampersand")), "&"),
    "& 'notepad'": (one(cmd("notepad", op="Ampersand")), "&"),
    ". .\\x.ps1": (one(cmd(".\\x.ps1", op="Dot")), "."),
    "iex 'calc'": (one(cmd("iex", q("calc"))), "Invoke-Expression"),
    "Invoke-Expression": (one(cmd("Invoke-Expression", q("x"))), "Invoke-Expression"),
    "icm": (one(cmd("icm", block(pipe(cmd("whoami"))))), "Invoke-Command"),
    "saps calc": (one(cmd("saps", s("calc"))), "Start-Process"),
    "start calc": (one(cmd("start", s("calc"))), "Start-Process"),
    "Start-Process -Verb RunAs": (
        one(cmd("Start-Process", s("powershell"), p("Verb"), s("RunAs"))),
        "Start-Process",
    ),
    "Add-Type": (one(cmd("Add-Type", q("x"))), "Add-Type"),
    "ii x.exe": (one(cmd("ii", s("x.exe"))), "Invoke-Item"),
    "New-Object -ComObject": (one(cmd("New-Object", p("ComObject"), s("WScript.Shell"))), "COM"),
    "New-Object -Com": (one(cmd("New-Object", p("Com"), s("WScript.Shell"))), "COM"),
    "Import-Module x": (one(cmd("Import-Module", s("x"))), "Import-Module"),
    "Set-ExecutionPolicy": (one(cmd("Set-ExecutionPolicy", s("Bypass"))), "Set-ExecutionPolicy"),
    "Register-ScheduledTask": (
        one(cmd("Register-ScheduledTask", s("x"))),
        "Register-ScheduledTask",
    ),
    "cmd /c": (one(cmd("cmd", s("/c"), s("del"), s("x"))), "cmd"),
    "cmd.exe": (one(cmd("cmd.exe", s("/c"), s("x"))), "cmd"),
    "full path to cmd": (one(cmd("C:\\Windows\\System32\\cmd.exe", s("/c"))), "cmd"),
    "powershell -enc": (one(cmd("powershell", p("enc"), s("AAAA"))), "powershell"),
    "pwsh": (one(cmd("pwsh", p("c"), q("x"))), "pwsh"),
    "python": (one(cmd("python", s("x.py"))), "python"),
    "wsl": (one(cmd("wsl", s("rm"))), "wsl"),
    "mshta": (one(cmd("mshta", s("x"))), "mshta"),
    "rundll32": (one(cmd("rundll32", s("x"))), "rundll32"),
    "certutil": (one(cmd("certutil", s("-urlcache"))), "certutil"),
    "forfiles": (one(cmd("forfiles", s("/c"), q("cmd"))), "forfiles"),
    "wmic": (one(cmd("wmic", s("process"), s("call"), s("create"))), "wmic"),
    "a script file": (one(cmd(".\\deploy.ps1")), "script"),
    "a bat file": (one(cmd("C:\\Windows\\x.bat")), "script"),
    "a relative program": (one(cmd(".\\tool.exe")), "Windows' own folders"),
    "a program outside Windows": (one(cmd("C:\\Users\\Boss\\tool.exe")), "Windows' own folders"),
    "a script block elsewhere": (one(cmd("Get-Item", block(pipe(cmd("x"))))), "script block"),
    "a command in a script block": (
        one(cmd("Get-ChildItem"), cmd("ForEach-Object", block(pipe(cmd("Remove-Item", var("_")))))),
        "inside a script block",
    ),
    "% Kill": (one(cmd("Get-Process"), cmd("%", s("Kill"))), "ForEach-Object"),
    "ForEach-Object -MemberName Kill": (
        one(cmd("Get-Process"), cmd("ForEach-Object", p("MemberName"), s("Kill"))),
        "ForEach-Object",
    ),
    "a method call": (
        one(cmd("Get-Process"), cmd("%", block(pipe(expr(call(var("_"), "Kill")))))),
        "InvokeMemberExpressionAst",
    ),
    "a static member": (
        one(expr(member(other("TypeExpressionAst", TypeName="IO.File"), "Delete", static=True))),
        "not allowed",
    ),
    "$(...)": (
        one(cmd("Get-Item", other("SubExpressionAst", script(pipe(cmd("x")))))),
        "SubExpressionAst",
    ),
    "an assignment": (
        script(other("AssignmentStatementAst", var("x"), expr(num(1)))),
        "AssignmentStatementAst",
    ),
    "> file": (
        one(cmd("Get-Process", other("FileRedirectionAst", s("out.txt")))),
        "FileRedirectionAst",
    ),
    "a variable": (one(cmd("Get-Item", var("env:TEMP"))), "$env:TEMP"),
    "splatting": (one(cmd("Get-Item", var("args", splatted=True))), "splat"),
    "$_ outside a block": (one(cmd("Get-Item", var("_"))), "$_"),
    "a computed command name": (one(cmd(xs("Remove-$x", var("x")))), "name"),
    # catastrophic
    "Remove-Item C:\\ -Recurse": (one(cmd("Remove-Item", s("C:\\"), p("Recurse"))), "protected"),
    "rm -r -fo C:\\": (one(cmd("rm", p("r"), p("fo"), s("C:\\"))), "protected"),
    "rd /s /q C:\\Windows": (one(cmd("rd", s("/s"), s("/q"), s("C:\\Windows"))), "protected"),
    "Remove-Item -Recurse -Path:C:\\Users": (
        one(cmd("Remove-Item", p("Recurse"), p("Path", s("C:\\Users")))),
        "protected",
    ),
    "Remove-Item ~ -Recurse": (one(cmd("Remove-Item", s("~"), p("Recurse"))), "protected"),
    "Remove-Item $HOME -Recurse": (one(cmd("Remove-Item", var("HOME"), p("Recurse"))), "protected"),
    "Remove-Item $env:USERPROFILE\\* -Recurse": (
        one(cmd("Remove-Item", xs("$env:USERPROFILE\\*", var("env:USERPROFILE")), p("Recurse"))),
        "protected",
    ),
    "Remove-Item ..\\.. -Recurse": (
        one(cmd("Remove-Item", s("..\\.."), p("Recurse"))),
        "protected",
    ),
    "Remove-Item C:\\Win* -Recurse": (
        one(cmd("Remove-Item", s("C:\\Win*"), p("Recurse"))),
        "protected",
    ),
    "Remove-Item 'C:\\Program Files\\App' -Recurse": (
        one(cmd("Remove-Item", q("C:\\Program Files\\App"), p("Recurse"))),
        "protected",
    ),
    "Remove-Item C:\\Windows\\System32\\drivers -Recurse": (
        one(cmd("Remove-Item", s("C:\\Windows\\System32\\drivers"), p("Recurse"))),
        "protected",
    ),
    "Remove-Item -LiteralPath x,C:\\ -Recurse": (
        one(cmd("Remove-Item", p("LiteralPath"), arr(s("x"), s("C:\\")), p("Recurse"))),
        "protected",
    ),
    "Remove-Item \\\\server\\share -Recurse": (
        one(cmd("Remove-Item", s("\\\\server\\share"), p("Recurse"))),
        "protected",
    ),
    "Remove-Item C:\\PROGRA~1 -Recurse": (
        one(cmd("Remove-Item", s("C:\\PROGRA~1\\x"), p("Recurse"))),
        "short",
    ),
    "Remove-Item HKLM:\\Software\\x": (
        one(cmd("Remove-Item", s("HKLM:\\Software\\x"))),
        "registry",
    ),
    "Set-ItemProperty HKLM:": (
        one(cmd("Set-ItemProperty", s("HKLM:\\System\\x"), s("y"), num(1))),
        "registry",
    ),
    "Remove-Item Registry::HKEY_LOCAL_MACHINE\\x": (
        one(cmd("Remove-Item", s("Registry::HKEY_LOCAL_MACHINE\\x"))),
        "registry",
    ),
    "a computed path": (one(cmd("Remove-Item", xs("$x", var("x")), p("Recurse"))), "$x"),
    "gci | Remove-Item": (one(cmd("Get-ChildItem", s("C:\\")), cmd("Remove-Item")), "pipeline"),
    "gps | Stop-Process": (one(cmd("Get-Process"), cmd("Stop-Process")), "pipeline"),
    "Stop-Process -Name lsass": (one(cmd("Stop-Process", p("Name"), s("lsass"))), "lsass"),
    "kill -Name *": (one(cmd("kill", p("Name"), s("*"))), "wildcard"),
    "spps -Id own": (one(cmd("spps", p("Id"), num(4242))), "Zeno"),
    "Stop-Process -Id 4": (one(cmd("Stop-Process", p("Id"), num(4))), "4"),
    "taskkill /im csrss.exe": (one(cmd("taskkill", s("/im"), s("csrss.exe"), s("/f"))), "csrss"),
    "taskkill /fi": (one(cmd("taskkill", s("/fi"), q("STATUS eq RUNNING"))), "filter"),
    "Format-Volume": (one(cmd("Format-Volume", p("DriveLetter"), s("D"))), "Format-Volume"),
    "Clear-Disk": (one(cmd("Clear-Disk", p("Number"), num(1))), "Clear-Disk"),
    "diskpart": (one(cmd("diskpart")), "diskpart"),
    "format d:": (one(cmd("format", s("d:"))), "format"),
    "cipher /w": (one(cmd("cipher", s("/w:C:\\"))), "cipher"),
    "vssadmin delete shadows": (
        one(cmd("vssadmin", s("delete"), s("shadows"), s("/all"))),
        "vssadmin",
    ),
    "Stop-Computer": (one(cmd("Stop-Computer")), "Stop-Computer"),
    "Restart-Computer": (one(cmd("Restart-Computer", p("Force"))), "Restart-Computer"),
    "shutdown /s": (one(cmd("shutdown", s("/s"))), "shutdown"),
    "Disable-BitLocker": (one(cmd("Disable-BitLocker", s("C:"))), "Disable-BitLocker"),
    "Set-MpPreference -DisableRealtimeMonitoring": (
        one(cmd("Set-MpPreference", p("DisableRealtimeMonitoring"), var("true"))),
        "Defender",
    ),
    "Add-MpPreference -ExclusionPath": (
        one(cmd("Add-MpPreference", p("ExclusionPath"), s("C:\\"))),
        "Defender",
    ),
    "Set-NetFirewallProfile": (
        one(cmd("Set-NetFirewallProfile", p("Enabled"), s("False"))),
        "Set-NetFirewallProfile",
    ),
    "netsh advfirewall": (
        one(cmd("netsh", s("advfirewall"), s("set"), s("allprofiles"), s("state"), s("off"))),
        "firewall",
    ),
    "net user": (one(cmd("net", s("user"), s("x"), s("/add"))), "accounts"),
    "net localgroup": (
        one(cmd("net", s("localgroup"), s("administrators"), s("x"), s("/add"))),
        "accounts",
    ),
    "New-LocalUser": (one(cmd("New-LocalUser", s("x"))), "New-LocalUser"),
    "Add-LocalGroupMember": (
        one(cmd("Add-LocalGroupMember", s("Administrators"))),
        "Add-LocalGroupMember",
    ),
    "Set-Acl": (one(cmd("Set-Acl", s("x"))), "Set-Acl"),
    "icacls": (one(cmd("icacls", s("C:\\"), s("/grant"), s("Everyone:F"))), "icacls"),
    "takeown": (one(cmd("takeown", s("/f"), s("C:\\Windows"))), "takeown"),
    "bcdedit": (one(cmd("bcdedit", s("/set"))), "bcdedit"),
    "reg delete HKLM": (one(cmd("reg", s("delete"), s("HKLM\\Software\\x"), s("/f"))), "registry"),
    "reg add HKEY_LOCAL_MACHINE": (
        one(cmd("reg.exe", s("add"), s("HKEY_LOCAL_MACHINE\\x"))),
        "registry",
    ),
    "schtasks /create": (one(cmd("schtasks", s("/create"), s("/tn"), s("x"))), "schtasks"),
    "sc create": (one(cmd("sc.exe", s("create"), s("x"))), "sc"),
}


@pytest.mark.parametrize("label", REFUSED)
def test_refused(label: str) -> None:
    tree, reason = REFUSED[label]
    extra = {"errors": ["Missing closing '}'"]} if label == "parse error" else {}
    assert reason.lower() in refused(tree, **extra).lower()


def test_the_helper_alias_table_is_used() -> None:
    tree = one(cmd("zap", s("C:\\"), p("Recurse")))
    check(tree)  # unknown to the fallback table: just a program name
    assert "protected" in refused(tree, aliases={"zap": "Remove-Item"})


def test_malformed_parser_output_is_refused() -> None:
    for raw in ("", "not json", "[]", '{"errors": [], "nodes": []}', '{"nodes": [{"id": 0}]}'):
        with pytest.raises(CommandRefused):
            check_powershell(parse_tree(raw), CTX)


def test_the_realpath_is_checked_too() -> None:
    # a junction in the projects folder that points at C:\Windows
    def realpath(path: str) -> str:
        return path.replace(HOME + "\\projects\\link", "C:\\Windows")

    ctx = PsContext(home=HOME, cwd=CTX.cwd, own_pid=1, realpath=realpath)
    tree = one(cmd("Remove-Item", s("link"), p("Recurse")))
    check(tree)  # lexically fine
    assert "protected" in refused(tree, ctx)


def test_the_folders_that_hold_a_deep_home_folder_are_protected() -> None:
    ctx = PsContext(home="D:\\Profiles\\Team\\Boss", cwd="D:\\Profiles\\Team\\Boss", own_pid=1)
    assert "home" in refused(one(cmd("Remove-Item", s("D:\\Profiles\\Team"), p("Recurse"))), ctx)
    check(one(cmd("Remove-Item", s("D:\\Profiles\\Team\\Other"), p("Recurse"))), ctx)


def test_device_paths_are_read_like_normal_ones() -> None:
    check(one(cmd("Remove-Item", s("\\\\?\\C:\\Users\\Boss\\projects\\old"), p("Recurse"))))
    assert "home" in refused(one(cmd("Remove-Item", s("\\\\?\\C:\\Users\\Boss"), p("Recurse"))))


# --- property: every spelling of "delete a protected folder" is refused --------------

PROTECTED = [
    "C:\\",
    "C:\\Windows",
    "C:\\Users",
    "C:\\Program Files",
    "C:\\Program Files (x86)\\Common Files",
    HOME,
    "C:\\Users\\Boss\\..",
    "D:\\",
    "C:\\Windows\\System32",
    "C:\\Data",
    "D:\\Backups",
]
REMOVERS = ["Remove-Item", "remove-item", "rm", "del", "erase", "rd", "rmdir", "ri", "RM"]


def spellings(path: str) -> st.SearchStrategy[str]:
    variants = [
        path,
        path.lower(),
        path.upper(),
        path.replace("\\", "/"),
        path.rstrip("\\") + "\\",
        path.rstrip("\\") + "\\.",
        path + ".",
        "\\\\?\\" + path,
        "Microsoft.PowerShell.Core\\FileSystem::" + path,
        path.rstrip("\\") + "\\*",
        path.rstrip("\\") + "\\x\\..",
    ]
    if path.lower().startswith(HOME.lower()):
        variants.append("~" + path[len(HOME) :])
    if path.lower().startswith("c:\\"):
        variants.append(path[2:] or "\\")  # rooted on the current drive
    return st.sampled_from(variants)


@settings(max_examples=2000, deadline=None)
@given(
    data=st.data(),
    remover=st.sampled_from(REMOVERS),
    flag=st.sampled_from(["r", "R", "Rec", "recurse", "RECURSE"]),
    quoting=st.sampled_from(["BareWord", "SingleQuoted", "DoubleQuoted"]),
    flag_first=st.booleans(),
    named=st.sampled_from([None, "Path", "LiteralPath", "PSPath", "LP", "pa"]),
)
def test_no_spelling_of_deleting_a_protected_folder_gets_through(
    data: st.DataObject, remover: str, flag: str, quoting: str, flag_first: bool, named: str | None
) -> None:
    target = data.draw(spellings(data.draw(st.sampled_from(PROTECTED))))
    value = s(target, quoting)
    path_args = [p(named), value] if named else [value]
    args = [p(flag), *path_args] if flag_first else [*path_args, p(flag)]
    with pytest.raises(CommandRefused):
        check(one(cmd(remover, *args)))


@settings(max_examples=300, deadline=None)
@given(
    name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=12),
    deep=st.integers(min_value=0, max_value=3),
)
def test_deleting_inside_a_project_folder_is_left_to_the_owner(name: str, deep: int) -> None:
    folder = ntpath.join(HOME, "projects", *(["sub"] * deep), name)
    if name in {".", ".."} or "~" in name:
        return
    check(one(cmd("Remove-Item", s(folder), p("Recurse"), p("Force"))))
