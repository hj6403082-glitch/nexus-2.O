"""ssh_run: one command on a host the owner listed, key auth, strict host keys."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncssh
import pytest
from pydantic import ValidationError

from zeno.agent.tools.base import Risk, Tool
from zeno.agent.tools.ssh import SshConfig, load_ssh_config, ssh_tools


@dataclass
class Server:
    port: int
    host_key: asyncssh.SSHKey
    client_key_file: Path
    commands: list[str]


def handle(commands: list[str]) -> Any:
    async def process(proc: asyncssh.SSHServerProcess[str]) -> None:
        command = proc.command or ""
        commands.append(command)
        if command == "uptime":
            proc.stdout.write(" 10:00 up 3 days\n")
            proc.exit(0)
        elif command == "flood":
            proc.stdout.write("y\n" * 50_000)
            proc.exit(0)
        elif command == "hang":
            await asyncio.sleep(30)
        else:
            proc.stderr.write(f"{command}: not found\n")
            proc.exit(127)

    return process


@pytest.fixture
async def server(tmp_path: Path) -> AsyncIterator[Server]:
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    client_key = asyncssh.generate_private_key("ssh-ed25519")
    client_key_file = tmp_path / "id_ed25519"
    client_key.write_private_key(str(client_key_file))
    commands: list[str] = []
    listener = await asyncssh.listen(
        "127.0.0.1",
        0,
        server_host_keys=[host_key],
        authorized_client_keys=asyncssh.import_authorized_keys(
            client_key.export_public_key().decode()
        ),
        process_factory=handle(commands),
    )
    port = listener.sockets[0].getsockname()[1]
    try:
        yield Server(port, host_key, client_key_file, commands)
    finally:
        listener.close()
        await listener.wait_closed()


def write_config(
    tmp_path: Path, server: Server, *, host_key: asyncssh.SSHKey | None = None
) -> Path:
    known = tmp_path / "known_hosts"
    public = (host_key or server.host_key).export_public_key().decode().strip()
    known.write_text(f"[127.0.0.1]:{server.port} {public}\n")
    path = tmp_path / "ssh_hosts.json"
    path.write_text(
        json.dumps(
            {
                "known_hosts": str(known),
                "hosts": {
                    "pi": {
                        "host": "127.0.0.1",
                        "port": server.port,
                        "user": "zeno",
                        "key_file": str(server.client_key_file),
                    }
                },
            }
        )
    )
    return path


def ssh_run(config_path: Path, **options: Any) -> Tool[Any]:
    config = load_ssh_config(config_path)
    assert config is not None
    (tool,) = ssh_tools(config, **options)
    return tool


def args(tool: Tool[Any], **values: Any) -> Any:
    return tool.args_model.model_validate(values)


# --- configuration ------------------------------------------------------------------


def test_no_hosts_file_means_no_tool(tmp_path: Path) -> None:
    assert load_ssh_config(tmp_path / "missing.json") is None


def test_an_empty_host_list_means_no_tool(tmp_path: Path) -> None:
    known = tmp_path / "known_hosts"
    known.write_text("")
    assert ssh_tools(SshConfig(known_hosts=known, hosts={})) == []


def test_a_known_hosts_file_is_required(tmp_path: Path, server: Server) -> None:
    path = write_config(tmp_path, server)
    (tmp_path / "known_hosts").unlink()
    with pytest.raises(ValueError, match="known_hosts"):
        load_ssh_config(path)


@pytest.mark.parametrize("alias", ["Pi", "a b", "-x", ""])
def test_aliases_are_plain_names(tmp_path: Path, alias: str) -> None:
    known = tmp_path / "known_hosts"
    known.write_text("")
    host = {"host": "10.0.0.2", "user": "zeno", "key_file": str(known)}
    with pytest.raises(ValidationError):
        SshConfig.model_validate({"known_hosts": str(known), "hosts": {alias: host}})


# --- the tool -----------------------------------------------------------------------


def test_ssh_run_is_privileged_and_names_only_listed_hosts(tmp_path: Path, server: Server) -> None:
    tool = ssh_run(write_config(tmp_path, server))
    assert tool.name == "ssh_run" and tool.risk is Risk.PRIVILEGED
    schema = tool.args_model.model_json_schema()
    host = schema["properties"]["host"]
    assert host.get("enum", [host.get("const")]) == ["pi"]
    with pytest.raises(ValidationError):
        args(tool, host="elsewhere", command="uptime")


@pytest.mark.parametrize("command", ["", "a\nb", "a\rb", "a\x00b", "x" * 1001])
def test_commands_are_one_bounded_line(tmp_path: Path, server: Server, command: str) -> None:
    tool = ssh_run(write_config(tmp_path, server))
    with pytest.raises(ValidationError):
        args(tool, host="pi", command=command)


async def test_runs_a_command_and_reports_its_exit(tmp_path: Path, server: Server) -> None:
    tool = ssh_run(write_config(tmp_path, server))
    text = await tool.invoke(args(tool, host="pi", command="uptime"))
    assert server.commands == ["uptime"]
    assert "exit 0" in text and "up 3 days" in text


async def test_errors_and_exit_codes_come_back(tmp_path: Path, server: Server) -> None:
    tool = ssh_run(write_config(tmp_path, server))
    text = await tool.invoke(args(tool, host="pi", command="nosuch"))
    assert "exit 127" in text and "nosuch: not found" in text


async def test_output_is_capped(tmp_path: Path, server: Server) -> None:
    tool = ssh_run(write_config(tmp_path, server), max_output=1000)
    text = await tool.invoke(args(tool, host="pi", command="flood"))
    assert len(text) < 1200 and "cut" in text


async def test_a_slow_command_times_out(tmp_path: Path, server: Server) -> None:
    tool = ssh_run(write_config(tmp_path, server), command_timeout=0.5)
    with pytest.raises(ValueError, match="did not finish"):
        await tool.invoke(args(tool, host="pi", command="hang"))


async def test_an_unknown_host_key_is_refused(tmp_path: Path, server: Server) -> None:
    impostor = asyncssh.generate_private_key("ssh-ed25519")
    tool = ssh_run(write_config(tmp_path, server, host_key=impostor))
    with pytest.raises(ValueError, match="could not connect"):
        await tool.invoke(args(tool, host="pi", command="uptime"))
    assert server.commands == []
