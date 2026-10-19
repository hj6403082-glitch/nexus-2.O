import json
from pathlib import Path

import pytest

from zeno.senses.auth import DeviceAuth, parse_bearer


def test_registered_device_verifies_with_its_token() -> None:
    auth = DeviceAuth()
    token = auth.register("pi-livingroom")
    assert len(token) >= 32
    assert auth.verify("pi-livingroom", token)


@pytest.mark.parametrize(
    ("device", "token"), [("pi-livingroom", "wrong"), ("unknown-pi", "x"), ("pi-livingroom", "")]
)
def test_rejects_bad_credentials(device: str, token: str) -> None:
    auth = DeviceAuth()
    auth.register("pi-livingroom")
    assert not auth.verify(device, token)


def test_tokens_are_not_interchangeable_between_devices() -> None:
    auth = DeviceAuth()
    kitchen = auth.register("pi-kitchen")
    auth.register("pi-garage")
    assert not auth.verify("pi-garage", kitchen)


def test_re_registering_rotates_the_token() -> None:
    auth = DeviceAuth()
    old = auth.register("pi-kitchen")
    new = auth.register("pi-kitchen")
    assert not auth.verify("pi-kitchen", old)
    assert auth.verify("pi-kitchen", new)


def test_revoke() -> None:
    auth = DeviceAuth()
    token = auth.register("pi-kitchen")
    assert auth.revoke("pi-kitchen") is True
    assert auth.revoke("pi-kitchen") is False
    assert not auth.verify("pi-kitchen", token)
    assert auth.devices() == []


@pytest.mark.parametrize("device", ["", "Pi Kitchen", "a", "x" * 49, "../etc"])
def test_rejects_invalid_device_ids(device: str) -> None:
    with pytest.raises(ValueError):
        DeviceAuth().register(device)


def test_persists_only_token_hashes(tmp_path: Path) -> None:
    path = tmp_path / "devices.json"
    token = DeviceAuth(path).register("pi-kitchen")
    assert token not in path.read_text()
    assert set(json.loads(path.read_text())) == {"pi-kitchen"}
    reloaded = DeviceAuth(path)
    assert reloaded.verify("pi-kitchen", token)
    assert reloaded.devices() == ["pi-kitchen"]


@pytest.mark.parametrize(
    ("header", "token"),
    [
        ("Bearer abc123", "abc123"),
        ("bearer abc123", "abc123"),
        ("Bearer ", None),
        ("Basic abc123", None),
        ("abc123", None),
        (None, None),
    ],
)
def test_parse_bearer(header: str | None, token: str | None) -> None:
    assert parse_bearer(header) == token
