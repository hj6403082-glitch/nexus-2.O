"""Read-only network diagnostics: ping, DNS lookup, one-port check, interface status."""

import asyncio
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import ValidationError

from zeno.agent.tools.base import Risk, Tool
from zeno.agent.tools.network import (
    DnsArgs,
    PingArgs,
    PortArgs,
    StatusArgs,
    network_tools,
)


@dataclass
class FakeHost:
    address: str
    is_alive: bool = True
    packets_sent: int = 3
    packets_received: int = 3
    packet_loss: float = 0.0
    min_rtt: float = 1.0
    avg_rtt: float = 2.5
    max_rtt: float = 4.0


@dataclass
class FakePinger:
    reply: FakeHost | Exception
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, address: str, **options: Any) -> FakeHost:
        self.calls.append({"address": address, **options})
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def tools(pinger: FakePinger | None = None) -> dict[str, Tool[Any]]:
    return {t.name: t for t in network_tools(pinger=pinger or FakePinger(FakeHost("10.0.0.1")))}


@pytest.fixture
async def listening_port() -> AsyncIterator[int]:
    async def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port: int = server.sockets[0].getsockname()[1]
    async with server:
        yield port


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


def test_the_network_tools_only_look() -> None:
    found = tools()
    assert sorted(found) == ["dns_lookup", "network_status", "ping", "port_check"]
    assert {t.risk for t in found.values()} == {Risk.READ_ONLY}


# --- arguments ----------------------------------------------------------------------


@pytest.mark.parametrize("host", ["example.com", "router.local", "192.168.1.1", "fe80::1", "a"])
def test_host_names_and_addresses_are_accepted(host: str) -> None:
    assert PingArgs(host=host).host == host


@pytest.mark.parametrize(
    "host", ["", "-oProxyCommand=x", "a b", "host;rm", "x" * 254, "../etc", "h\n", "a..b"]
)
def test_anything_but_a_host_is_refused(host: str) -> None:
    with pytest.raises(ValidationError):
        PingArgs(host=host)


@pytest.mark.parametrize("count", [0, 11])
def test_ping_count_is_bounded(count: int) -> None:
    with pytest.raises(ValidationError):
        PingArgs(host="example.com", count=count)


@pytest.mark.parametrize("port", [0, 65536, -1])
def test_port_is_a_real_port(port: int) -> None:
    with pytest.raises(ValidationError):
        PortArgs(host="example.com", port=port)


def test_port_check_takes_exactly_one_port() -> None:
    with pytest.raises(ValidationError):
        PortArgs.model_validate({"host": "example.com", "port": 22, "ports": [1, 2]})


# --- ping ---------------------------------------------------------------------------


async def test_ping_reports_round_trip_times() -> None:
    pinger = FakePinger(FakeHost("10.0.0.1"))
    text = await tools(pinger)["ping"].invoke(PingArgs(host="10.0.0.1", count=3))
    assert "10.0.0.1 is reachable" in text
    assert "3/3" in text and "2.5 ms" in text
    assert pinger.calls[0]["address"] == "10.0.0.1"
    assert pinger.calls[0]["count"] == 3
    assert pinger.calls[0]["privileged"] is False


async def test_ping_reports_an_unreachable_host() -> None:
    host = FakeHost("10.0.0.9", is_alive=False, packets_received=0, packet_loss=1.0)
    text = await tools(FakePinger(host))["ping"].invoke(PingArgs(host="10.0.0.9"))
    assert "did not answer" in text and "0/3" in text


async def test_ping_failure_becomes_a_readable_error() -> None:
    pinger = FakePinger(OSError("Operation not permitted"))
    with pytest.raises(ValueError, match="could not ping"):
        await tools(pinger)["ping"].invoke(PingArgs(host="10.0.0.1"))


# --- DNS ----------------------------------------------------------------------------


async def test_dns_lookup_resolves_localhost() -> None:
    text = await tools()["dns_lookup"].invoke(DnsArgs(name="localhost"))
    assert "127.0.0.1" in text or "::1" in text


async def test_dns_lookup_can_ask_for_ipv4_only() -> None:
    text = await tools()["dns_lookup"].invoke(DnsArgs(name="localhost", family="ipv4"))
    assert "127.0.0.1" in text and "::1" not in text


async def test_dns_lookup_reports_an_unknown_name() -> None:
    with pytest.raises(ValueError, match="could not resolve"):
        await tools()["dns_lookup"].invoke(DnsArgs(name="no-such-host.invalid"))


# --- port check ---------------------------------------------------------------------


async def test_port_check_sees_an_open_port(listening_port: int) -> None:
    text = await tools()["port_check"].invoke(PortArgs(host="127.0.0.1", port=listening_port))
    assert text.startswith(f"Port {listening_port} on 127.0.0.1 is open")


async def test_port_check_sees_a_closed_port() -> None:
    port = closed_port()
    text = await tools()["port_check"].invoke(PortArgs(host="127.0.0.1", port=port))
    assert text.startswith(f"Port {port} on 127.0.0.1 is closed")


# --- status -------------------------------------------------------------------------


async def test_network_status_lists_the_loopback_interface() -> None:
    text = await tools()["network_status"].invoke(StatusArgs())
    assert "127.0.0.1" in text
    assert "sent" in text and "received" in text
