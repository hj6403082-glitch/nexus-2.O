"""Web search through the owner's SearXNG, and page fetches that cannot reach the LAN."""

import asyncio
import ipaddress
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import ValidationError

from zeno.agent.tools.base import Risk, Tool
from zeno.agent.tools.web import (
    FetchArgs,
    FetchPolicy,
    SearchArgs,
    address_allowed,
    web_tools,
)

Route = tuple[int, dict[str, str], bytes]


@dataclass
class Site:
    """A tiny HTTP/1.1 server on 127.0.0.1 that answers from a route table."""

    routes: dict[str, Route]
    hits: list[str] = field(default_factory=list)
    port: int = 0

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        path = head.split(b" ")[1].decode()
        self.hits.append(path)
        status, headers, body = self.routes.get(path.split("?")[0], (404, {}, b"missing"))
        lines = [f"HTTP/1.1 {status} X", f"Content-Length: {len(body)}", "Connection: close"]
        lines += [f"{k}: {v}" for k, v in headers.items()]
        writer.write(("\r\n".join(lines) + "\r\n\r\n").encode() + body)
        await writer.drain()
        writer.close()


@pytest.fixture
async def site() -> AsyncIterator[Site]:
    page = b"<html><head><title>T</title><script>evil()</script><style>p{}</style></head>"
    page += b"<body><h1>Hello</h1><p>Zeno reads <b>this</b>.</p></body></html>"
    s = Site(
        {
            "/page": (200, {"Content-Type": "text/html; charset=utf-8"}, page),
            "/plain": (200, {"Content-Type": "text/plain"}, b"just text"),
            "/image": (200, {"Content-Type": "image/png"}, b"\x89PNG"),
            "/huge": (200, {"Content-Type": "text/plain"}, b"x" * 300_000),
            "/hop": (302, {"Location": "/page"}, b""),
            "/to-lan": (302, {"Location": "http://intranet.test/secret"}, b""),
            "/loop": (302, {"Location": "/loop"}, b""),
        }
    )
    server = await asyncio.start_server(s.handle, "127.0.0.1", 0)
    s.port = server.sockets[0].getsockname()[1]
    async with server:
        yield s


def resolver(table: dict[str, list[str]]) -> Callable[[str, int], Any]:
    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError(f"unknown host {host}")
        return table[host]

    return resolve


NAMES = {
    "site.test": ["127.0.0.1"],
    "intranet.test": ["10.0.0.5"],
    "mixed.test": ["8.8.8.8", "127.0.0.1"],
}


def loopback_only(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Tests stand the 'public internet' up on 127.0.0.1; nothing else is reachable."""
    return ip.is_loopback


def fetcher(*, allowed: Any = loopback_only, max_bytes: int = 100_000) -> Tool[Any]:
    policy = FetchPolicy(max_bytes=max_bytes, max_chars=500, timeout=5.0)
    found = web_tools(fetch=policy, resolve=resolver(NAMES), address_allowed=allowed)
    return {t.name: t for t in found}["fetch_page"]


# --- which tools exist --------------------------------------------------------------


def test_nothing_is_offered_until_configured() -> None:
    assert web_tools() == []


def test_web_tools_only_look() -> None:
    found = web_tools(search_url="http://127.0.0.1:8888", fetch=FetchPolicy())
    assert sorted(t.name for t in found) == ["fetch_page", "web_search"]
    assert {t.risk for t in found} == {Risk.READ_ONLY}


# --- address policy -----------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "192.168.1.10",
        "172.16.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",  # noqa: S104 (an address to refuse, not a bind)
        "224.0.0.1",
        "::1",
        "fe80::1",
        "fd00::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
    ],
)
def test_private_and_special_addresses_are_refused(address: str) -> None:
    assert not address_allowed(ipaddress.ip_address(address))


@pytest.mark.parametrize("address", ["8.8.8.8", "93.184.216.34", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(address: str) -> None:
    assert address_allowed(ipaddress.ip_address(address))


def test_the_lan_can_be_allowed_but_never_this_machine() -> None:
    assert address_allowed(ipaddress.ip_address("192.168.1.10"), allow_lan=True)
    assert not address_allowed(ipaddress.ip_address("127.0.0.1"), allow_lan=True)
    assert not address_allowed(ipaddress.ip_address("169.254.169.254"), allow_lan=True)


# --- arguments ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://x.test/", "javascript:alert(1)", "http://", "x" * 3000]
)
def test_only_web_urls_are_accepted(url: str) -> None:
    with pytest.raises(ValidationError):
        FetchArgs(url=url)


def test_urls_with_credentials_are_refused() -> None:
    with pytest.raises(ValidationError):
        FetchArgs(url="http://user:pass@site.test/")


@pytest.mark.parametrize("query", ["", "q" * 301])
def test_search_queries_are_bounded(query: str) -> None:
    with pytest.raises(ValidationError):
        SearchArgs(query=query)


# --- fetching -----------------------------------------------------------------------


async def test_fetch_turns_html_into_labelled_text(site: Site) -> None:
    text = await fetcher().invoke(FetchArgs(url=f"http://site.test:{site.port}/page"))
    assert "Hello" in text and "Zeno reads this." in text
    assert "evil()" not in text and "p{}" not in text
    assert text.startswith("[Web page http://site.test:")
    assert "not instructions" in text.splitlines()[0]


async def test_fetch_returns_plain_text(site: Site) -> None:
    text = await fetcher().invoke(FetchArgs(url=f"http://site.test:{site.port}/plain"))
    assert text.endswith("just text")


async def test_fetch_refuses_binary_content(site: Site) -> None:
    with pytest.raises(ValueError, match="not text"):
        await fetcher().invoke(FetchArgs(url=f"http://site.test:{site.port}/image"))


async def test_fetch_stops_reading_at_the_byte_cap(site: Site) -> None:
    with pytest.raises(ValueError, match="larger than"):
        await fetcher(max_bytes=10_000).invoke(FetchArgs(url=f"http://site.test:{site.port}/huge"))


async def test_fetch_caps_the_text_it_hands_back(site: Site) -> None:
    tool = web_tools(
        fetch=FetchPolicy(max_bytes=1_000_000, max_chars=500),
        resolve=resolver(NAMES),
        address_allowed=loopback_only,
    )[0]
    text = await tool.invoke(FetchArgs(url=f"http://site.test:{site.port}/huge"))
    assert len(text) < 700 and "cut" in text


async def test_fetch_follows_a_redirect(site: Site) -> None:
    text = await fetcher().invoke(FetchArgs(url=f"http://site.test:{site.port}/hop"))
    assert "Hello" in text and site.hits == ["/hop", "/page"]


async def test_the_default_policy_cannot_reach_this_machine(site: Site) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        await fetcher(allowed=address_allowed).invoke(
            FetchArgs(url=f"http://site.test:{site.port}/page")
        )
    assert site.hits == []


async def test_a_literal_private_address_is_refused(site: Site) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        await fetcher(allowed=address_allowed).invoke(
            FetchArgs(url=f"http://127.0.0.1:{site.port}/page")
        )
    assert site.hits == []


async def test_a_redirect_into_the_lan_is_refused(site: Site) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        await fetcher().invoke(FetchArgs(url=f"http://site.test:{site.port}/to-lan"))
    assert site.hits == ["/to-lan"]


async def test_a_name_with_any_private_address_is_refused(site: Site) -> None:
    # A rebinding name that also lists a public address still cannot pick the private one.
    allowed = lambda ip: not ip.is_loopback  # noqa: E731
    with pytest.raises(ValueError, match="not allowed"):
        await fetcher(allowed=allowed).invoke(FetchArgs(url=f"http://mixed.test:{site.port}/"))


async def test_redirect_loops_end(site: Site) -> None:
    with pytest.raises(ValueError, match="redirect"):
        await fetcher().invoke(FetchArgs(url=f"http://site.test:{site.port}/loop"))
    assert len(site.hits) <= 6


# --- searching ----------------------------------------------------------------------


async def test_search_reads_searxng_json(site: Site) -> None:
    results = {
        "results": [
            {"title": f"Result {i}", "url": f"https://r{i}.test/", "content": f"About {i}."}
            for i in range(10)
        ]
    }
    site.routes["/search"] = (
        200,
        {"Content-Type": "application/json"},
        json.dumps(results).encode(),
    )
    (search,) = web_tools(search_url=f"http://127.0.0.1:{site.port}")
    text = await search.invoke(SearchArgs(query="zeno brain", count=3))
    assert site.hits[0].startswith("/search?")
    assert "q=zeno+brain" in site.hits[0] and "format=json" in site.hits[0]
    assert "Result 0" in text and "https://r2.test/" in text and "Result 3" not in text
    assert "not instructions" in text.splitlines()[0]


async def test_search_with_no_results_says_so(site: Site) -> None:
    site.routes["/search"] = (200, {"Content-Type": "application/json"}, b'{"results": []}')
    (search,) = web_tools(search_url=f"http://127.0.0.1:{site.port}/")
    assert "No results" in await search.invoke(SearchArgs(query="nothing"))


async def test_search_failure_is_readable(site: Site) -> None:
    site.routes["/search"] = (500, {}, b"down")
    (search,) = web_tools(search_url=f"http://127.0.0.1:{site.port}")
    with pytest.raises(ValueError, match="search failed"):
        await search.invoke(SearchArgs(query="anything"))
