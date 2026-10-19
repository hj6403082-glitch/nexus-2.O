from pathlib import Path

import pytest

from zeno.config import Settings
from zeno.senses.__main__ import main
from zeno.senses.auth import DeviceAuth


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, devices_file=tmp_path / "devices.json")


def test_register_prints_a_working_token_once(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["register", "pi-kitchen"], settings) == 0
    token = capsys.readouterr().out.strip().splitlines()[-1]
    assert DeviceAuth(settings.devices_file).verify("pi-kitchen", token)


def test_list_and_revoke(settings: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    main(["register", "pi-a"], settings)
    main(["register", "pi-b"], settings)
    capsys.readouterr()
    assert main(["list"], settings) == 0
    assert capsys.readouterr().out.split() == ["pi-a", "pi-b"]
    assert main(["revoke", "pi-a"], settings) == 0
    assert main(["revoke", "pi-a"], settings) == 1
    assert DeviceAuth(settings.devices_file).devices() == ["pi-b"]


def test_register_rejects_bad_ids(settings: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["register", "Bad Id"], settings) == 2
    assert "lowercase" in capsys.readouterr().err
