"""A "Send to Zeno" entry in the Windows Explorer right-click menu.

Writes per-user keys under ``HKCU\\Software\\Classes`` (no admin needed): one for
files, one for folders. Each runs a short, windowless client that hands the
selected path to Zeno's loopback WebSocket. The ``winreg`` module is imported
lazily and can be injected, so the tests run against a fake registry on any OS and
never touch the real one.

    python -m zeno.hostos.windows.shell_integration --install
    python -m zeno.hostos.windows.shell_integration --remove
"""

import contextlib
import sys
from typing import Any, Protocol, cast

LABEL = "Send to Zeno"
CLIENT_MODULE = "zeno.hostos.windows.send_to_zeno"

# Under HKCU\Software\Classes. "*" is every file; "Directory" is a folder.
_BASES = (r"Software\Classes\*\shell\ZenoSendTo", r"Software\Classes\Directory\shell\ZenoSendTo")


class Registry(Protocol):
    HKEY_CURRENT_USER: Any
    REG_SZ: Any

    def CreateKey(self, root: Any, sub_key: str) -> Any: ...

    def SetValueEx(self, key: Any, name: str, reserved: int, type: Any, value: str) -> None: ...

    def CloseKey(self, key: Any) -> None: ...

    def DeleteKey(self, root: Any, sub_key: str) -> None: ...


def _winreg() -> Registry:
    import winreg  # Windows only

    return cast("Registry", winreg)


def build_command(pythonw: str) -> str:
    """The command Explorer runs; ``%1`` is the clicked path."""
    return f'"{pythonw}" -m {CLIENT_MODULE} "%1"'


def install(command: str, *, label: str = LABEL, registry: Registry | None = None) -> None:
    """Add the menu entry for files and folders. Overwrites any earlier entry."""
    reg = registry or _winreg()
    for base in _BASES:
        menu = reg.CreateKey(reg.HKEY_CURRENT_USER, base)
        try:
            reg.SetValueEx(menu, "", 0, reg.REG_SZ, label)
        finally:
            reg.CloseKey(menu)
        action = reg.CreateKey(reg.HKEY_CURRENT_USER, base + r"\command")
        try:
            reg.SetValueEx(action, "", 0, reg.REG_SZ, command)
        finally:
            reg.CloseKey(action)


def remove(*, registry: Registry | None = None) -> None:
    """Delete the menu entry. A missing entry is fine. Leaf keys go first."""
    reg = registry or _winreg()
    for base in _BASES:
        for sub_key in (base + r"\command", base):
            with contextlib.suppress(FileNotFoundError):
                reg.DeleteKey(reg.HKEY_CURRENT_USER, sub_key)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--remove" in args:
        remove()
        print("Removed the 'Send to Zeno' menu entry.")
        return 0
    if "--install" in args:
        install(build_command(sys.executable.replace("python.exe", "pythonw.exe")))
        print("Added 'Send to Zeno' to the right-click menu for files and folders.")
        return 0
    print("usage: python -m zeno.hostos.windows.shell_integration --install | --remove")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
