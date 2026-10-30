"""Read-only network diagnostics: ping, DNS lookup, one-port check, interface status.

Everything here runs in Python (unprivileged ICMP sockets, asyncio, psutil), so no
tool starts a process, and ``port_check`` connects to exactly one port: no scans.
"""

import asyncio
import contextlib
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal, Protocol

import icmplib
import psutil
from pydantic import AfterValidator, Field, StringConstraints

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool

_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def _host(value: str) -> str:
    """A DNS name or an IP address; nothing a shell or option parser could misread."""
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    labels = value.removesuffix(".").split(".")
    if not all(_LABEL.fullmatch(label) for label in labels):
        raise ValueError("must be a host name or an IP address")
    return value


# The pattern keeps the grammar close; the validator checks each label exactly.
Host = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9:][A-Za-z0-9.:-]{0,252}$", max_length=253),
    AfterValidator(_host),
]


class PingResult(Protocol):
    address: str
    is_alive: bool
    packets_sent: int
    packets_received: int
    packet_loss: float
    min_rtt: float
    avg_rtt: float
    max_rtt: float


Pinger = Callable[..., Awaitable[PingResult]]


class PingArgs(ToolArgs):
    host: Host
    count: int = Field(3, ge=1, le=10, description="Echo requests to send.")


class DnsArgs(ToolArgs):
    name: Host
    family: Literal["any", "ipv4", "ipv6"] = "any"


class PortArgs(ToolArgs):
    host: Host
    port: int = Field(ge=1, le=65535)


class StatusArgs(ToolArgs):
    pass


_FAMILIES = {"any": socket.AF_UNSPEC, "ipv4": socket.AF_INET, "ipv6": socket.AF_INET6}


def network_tools(*, pinger: Pinger | None = None, connect_timeout: float = 3.0) -> list[Tool[Any]]:
    """The diagnostics tools. ``pinger`` replaces icmplib in tests."""
    send_ping: Pinger = pinger or icmplib.async_ping

    @tool(risk=Risk.READ_ONLY, timeout=15.0)
    async def ping(args: PingArgs) -> str:
        """Ping a host and report whether it answers and how fast."""
        try:
            result = await send_ping(
                args.host, count=args.count, interval=0.5, timeout=2, privileged=False
            )
        except Exception as error:  # icmplib raises its own errors and OSError
            raise ValueError(f"could not ping {args.host}: {error}") from error
        who = args.host if result.address == args.host else f"{args.host} ({result.address})"
        answered = f"{result.packets_received}/{result.packets_sent} replies"
        if not result.is_alive:
            return f"{who} did not answer: {answered}."
        return (
            f"{who} is reachable: {answered}, round trip "
            f"min {result.min_rtt:.1f} ms, avg {result.avg_rtt:.1f} ms, "
            f"max {result.max_rtt:.1f} ms."
        )

    @tool(risk=Risk.READ_ONLY, timeout=10.0)
    async def dns_lookup(args: DnsArgs) -> str:
        """Look up the IP addresses a host name resolves to."""
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(
                args.name, None, family=_FAMILIES[args.family], type=socket.SOCK_STREAM
            )
        except OSError as error:
            raise ValueError(f"could not resolve {args.name}: {error}") from error
        addresses = sorted({str(info[4][0]) for info in infos})
        if not addresses:
            raise ValueError(f"could not resolve {args.name}: no addresses")
        return f"{args.name} resolves to {', '.join(addresses)}."

    @tool(risk=Risk.READ_ONLY, timeout=connect_timeout + 2.0)
    async def port_check(args: PortArgs) -> str:
        """Check whether one TCP port on a host accepts connections."""
        where = f"Port {args.port} on {args.host}"
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(args.host, args.port), connect_timeout
            )
        except TimeoutError:
            return f"{where} did not answer within {connect_timeout:g} s (filtered or down)."
        except OSError as error:
            return f"{where} is closed or unreachable ({error.strerror or error})."
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()
        return f"{where} is open."

    @tool(risk=Risk.READ_ONLY, timeout=5.0)
    async def network_status(args: StatusArgs) -> str:
        """List this computer's network interfaces: state, addresses and traffic so far."""
        return await asyncio.to_thread(_interfaces)

    return [ping, dns_lookup, port_check, network_status]


def _interfaces() -> str:
    stats = psutil.net_if_stats()
    counters = psutil.net_io_counters(pernic=True)
    lines = []
    for name, addrs in sorted(psutil.net_if_addrs().items()):
        stat = stats.get(name)
        state = "up" if stat is not None and stat.isup else "down"
        ips = [a.address for a in addrs if a.family in (socket.AF_INET, socket.AF_INET6)]
        line = f"- {name}: {state}, {', '.join(ips) or 'no IP address'}"
        io = counters.get(name)
        if io is not None:
            line += f"; sent {_size(io.bytes_sent)}, received {_size(io.bytes_recv)}"
        lines.append(line)
    return "\n".join(lines) if lines else "No network interfaces found."


def _size(count: int) -> str:
    value = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
