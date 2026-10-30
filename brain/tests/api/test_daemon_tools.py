"""Phase 2 tools join the daemon only when the owner configured them."""

import json
import platform
import socket
import sys
from pathlib import Path

import asyncssh
import pytest
from pydantic import ValidationError

from tests.api.conftest import brain_settings
from tests.api.test_daemon import Log, make_daemon
from zeno.agent.tools.ssh import SshConfig
from zeno.senses.mqtt import load_mqtt_config

OPTIONAL = {
    "ping",
    "dns_lookup",
    "port_check",
    "network_status",
    "web_search",
    "fetch_page",
    "ssh_run",
    "mqtt_read",
    "actuate_fan",
}


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


async def test_a_fresh_install_has_no_outbound_tools(tmp_path: Path) -> None:
    daemon, _ = make_daemon(tmp_path, Log())
    await daemon.start()
    try:
        assert OPTIONAL.isdisjoint(daemon.services.base_tools)
    finally:
        await daemon.stop()


async def test_configured_tools_are_offered(tmp_path: Path) -> None:
    known = tmp_path / "known_hosts"
    known.write_text("")
    key = tmp_path / "id_ed25519"
    asyncssh.generate_private_key("ssh-ed25519").write_private_key(str(key))
    (tmp_path / "ssh_hosts.json").write_text(
        json.dumps(
            {
                "known_hosts": str(known),
                "hosts": {"pi": {"host": "127.0.0.1", "user": "zeno", "key_file": str(key)}},
            }
        )
    )
    (tmp_path / "mqtt.json").write_text(
        json.dumps(
            {
                "broker": {"host": "127.0.0.1", "port": closed_port()},
                "read": [{"name": "room.temperature", "topic": "home/room"}],
                "actuators": [
                    {
                        "name": "fan",
                        "description": "The fan.",
                        "topic": "home/fan/set",
                        "payload": {"on": {"type": "bool"}},
                    }
                ],
            }
        )
    )
    daemon, _ = make_daemon(
        tmp_path,
        Log(),
        network_tools=True,
        web_search_url="http://127.0.0.1:8888",
        web_fetch=True,
    )
    await daemon.start()
    try:
        assert set(daemon.services.base_tools) >= OPTIONAL
        assert daemon.mqtt is not None
    finally:
        await daemon.stop()
    assert daemon.mqtt is None


async def test_a_broken_ssh_hosts_file_stops_the_boot(tmp_path: Path) -> None:
    (tmp_path / "ssh_hosts.json").write_text('{"hosts": {}}')
    daemon, _ = make_daemon(tmp_path, Log())
    with pytest.raises(Exception, match="known_hosts"):
        await daemon.start()
    assert daemon.state == "failed"


@pytest.mark.parametrize("url", ["ftp://search.lan", "searx.lan", "file:///etc"])
def test_the_search_url_must_be_web_address(tmp_path: Path, url: str) -> None:
    with pytest.raises(ValidationError):
        brain_settings(tmp_path, web_search_url=url)


def test_the_example_configs_are_valid() -> None:
    examples = Path(__file__).parents[2] / "examples"
    mqtt = load_mqtt_config(examples / "mqtt.example.json")
    assert mqtt is not None and mqtt.actuators
    ssh = SshConfig.model_validate_json((examples / "ssh_hosts.example.json").read_text())
    assert "pi" in ssh.hosts


LINUX = {
    "system_health",
    "system_temperatures",
    "top_processes",
    "process_info",
    "notify_desktop",
    "service_status",
    "run_command",
}


async def test_os_tools_are_off_until_turned_on(tmp_path: Path) -> None:
    daemon, _ = make_daemon(tmp_path, Log())
    await daemon.start()
    try:
        assert LINUX.isdisjoint(daemon.services.base_tools)
        assert "run_powershell" not in daemon.services.base_tools
    finally:
        await daemon.stop()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux tools")
async def test_linux_tools_join_when_turned_on(tmp_path: Path) -> None:
    daemon, _ = make_daemon(
        tmp_path, Log(), os_tools=True, run_command=True, run_command_roots=[tmp_path]
    )
    await daemon.start()
    try:
        assert set(daemon.services.base_tools) >= LINUX
        assert daemon.services.base_tools["run_command"].risk.value == "privileged"
    finally:
        await daemon.stop()


async def test_the_daemon_loads_the_windows_toolset_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    daemon, _ = make_daemon(
        tmp_path, Log(), os_tools=True, run_command=True, run_command_roots=[tmp_path]
    )
    await daemon.start()
    try:
        tools = daemon.services.base_tools
        assert "run_powershell" in tools and "run_command" not in tools
        assert tools["run_powershell"].risk.value == "privileged"
    finally:
        await daemon.stop()


async def test_other_systems_get_telemetry_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    daemon, _ = make_daemon(tmp_path, Log(), os_tools=True, run_command=True)
    await daemon.start()
    try:
        assert "system_health" in daemon.services.base_tools
        assert "run_command" not in daemon.services.base_tools
        assert "notify_desktop" not in daemon.services.base_tools
    finally:
        await daemon.stop()
