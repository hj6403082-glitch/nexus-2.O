"""ssh_run: one command on a machine the owner listed, with the owner's approval every time.

Hosts come from ``data/ssh_hosts.json``; the model can only name one of their aliases
(the grammar holds it to that list). Authentication is by key only, host keys must
already be in the owner's known_hosts file, and no OpenSSH config, agent, forwarding
or password is used.
"""

import asyncio
import dataclasses
import json
import typing
from pathlib import Path
from typing import Annotated, Any, Literal

import asyncssh
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, create_model

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool

Alias = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]


class SshHost(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(22, ge=1, le=65535)
    user: str = Field(min_length=1, max_length=64)
    key_file: Path


class SshConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    known_hosts: Path
    hosts: dict[Alias, SshHost] = Field(default_factory=dict, max_length=32)


def _one_line(value: str) -> str:
    if any(char in value for char in "\r\n\x00"):
        raise ValueError("must be a single line")
    return value


class SshArgs(ToolArgs):
    host: str = Field(description="One of the listed host aliases.")
    command: Annotated[str, Field(min_length=1, max_length=1000), AfterValidator(_one_line)]


def load_ssh_config(path: Path) -> SshConfig | None:
    """The owner's SSH hosts, or None when the file does not exist."""
    if not path.exists():
        return None
    config = SshConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
    known = config.known_hosts.expanduser()
    if not known.is_file():
        raise ValueError(f"the known_hosts file {known} is missing; SSH needs it")
    return config


def ssh_tools(
    config: SshConfig,
    *,
    command_timeout: float = 20.0,
    connect_timeout: float = 10.0,
    max_output: int = 8000,
) -> list[Tool[Any]]:
    if not config.hosts:
        return []
    hosts = config.hosts
    known_hosts = str(config.known_hosts.expanduser())

    @tool(risk=Risk.PRIVILEGED, timeout=connect_timeout + command_timeout + 5.0)
    async def ssh_run(args: SshArgs) -> str:
        """Run one shell command on one of the owner's machines over SSH and return its output.
        Listed hosts only; every call needs the owner's approval."""
        target = hosts[args.host]
        try:
            async with asyncssh.connect(
                target.host,
                target.port,
                config=None,
                known_hosts=known_hosts,
                username=target.user,
                client_keys=[str(target.key_file.expanduser())],
                agent_path=None,
                agent_forwarding=False,
                password_auth=False,
                kbdint_auth=False,
                host_based_auth=False,
                gss_auth=False,
                gss_kex=False,
                x11_forwarding=False,
                connect_timeout=connect_timeout,
                login_timeout=connect_timeout,
            ) as conn:
                return await _run(conn, args.host, args.command, command_timeout, max_output)
        except (OSError, asyncssh.Error) as error:
            raise ValueError(f"could not connect to {args.host}: {error}") from error

    # Narrow the host field to the listed aliases, so the grammar can only name those.
    names = typing.cast("Any", Literal).__getitem__(tuple(hosts))
    model = create_model(
        "SshArgs", __base__=SshArgs, host=(names, Field(description=f"One of: {', '.join(hosts)}."))
    )
    return [dataclasses.replace(ssh_run, args_model=model)]


async def _run(
    conn: asyncssh.SSHClientConnection, alias: str, command: str, seconds: float, cap: int
) -> str:
    output: list[str] = []
    size = 0
    cut = False
    try:
        async with asyncio.timeout(seconds):
            async with conn.create_process(
                command, stdin=asyncssh.DEVNULL, stderr=asyncssh.STDOUT
            ) as process:
                while chunk := await process.stdout.read(4096):
                    output.append(chunk)
                    size += len(chunk)
                    if size > cap:
                        cut = True
                        process.close()
                        break
                result = await process.wait(check=False)
    except TimeoutError:
        raise ValueError(f"{command!r} on {alias} did not finish within {seconds:g} s") from None
    text = "".join(output)
    if cut:
        text = text[:cap] + f"\n[... output cut at {cap} characters]"
    status = "killed" if result.exit_status is None else f"exit {result.exit_status}"
    return f"[ssh {alias}: {status}]\n{text.rstrip()}"
