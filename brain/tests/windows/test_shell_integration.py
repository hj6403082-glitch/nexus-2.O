"""The "Send to Zeno" context-menu entry, checked against a fake registry."""

from typing import Any

from zeno.hostos.windows import shell_integration as shell


class FakeRegistry:
    """The slice of winreg the module uses, backed by a dict of path -> values."""

    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self) -> None:
        self.keys: dict[str, dict[str, str]] = {}

    def CreateKey(self, root: Any, sub_key: str) -> str:
        assert root == self.HKEY_CURRENT_USER
        self.keys.setdefault(sub_key, {})
        return sub_key

    def SetValueEx(self, key: str, name: str, reserved: int, type: Any, value: str) -> None:
        assert type == self.REG_SZ
        self.keys[key][name] = value

    def CloseKey(self, key: str) -> None:
        pass

    def DeleteKey(self, root: Any, sub_key: str) -> None:
        assert root == self.HKEY_CURRENT_USER
        if sub_key not in self.keys:
            raise FileNotFoundError(sub_key)
        del self.keys[sub_key]


def test_build_command_quotes_and_passes_the_path() -> None:
    command = shell.build_command(r"C:\zeno\.venv\Scripts\pythonw.exe")
    assert command == (
        r'"C:\zeno\.venv\Scripts\pythonw.exe" -m zeno.hostos.windows.send_to_zeno "%1"'
    )


def test_install_writes_the_entry_for_files_and_folders() -> None:
    reg = FakeRegistry()
    shell.install("CMD", registry=reg)
    for base in (
        r"Software\Classes\*\shell\ZenoSendTo",
        r"Software\Classes\Directory\shell\ZenoSendTo",
    ):
        assert reg.keys[base][""] == "Send to Zeno"
        assert reg.keys[base + r"\command"][""] == "CMD"


def test_remove_deletes_every_key_leaf_first() -> None:
    reg = FakeRegistry()
    shell.install("CMD", registry=reg)
    shell.remove(registry=reg)
    assert reg.keys == {}


def test_remove_is_fine_when_nothing_is_installed() -> None:
    reg = FakeRegistry()
    shell.remove(registry=reg)  # must not raise
    assert reg.keys == {}


def test_reinstall_overwrites_the_command() -> None:
    reg = FakeRegistry()
    shell.install("OLD", registry=reg)
    shell.install("NEW", registry=reg)
    assert reg.keys[r"Software\Classes\*\shell\ZenoSendTo\command"][""] == "NEW"
