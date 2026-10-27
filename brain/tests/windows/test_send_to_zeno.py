"""The "Send to Zeno" client builds a valid chat frame and sends it once."""

import json
from contextlib import contextmanager
from typing import Any

from zeno.api.protocol import parse_inbound
from zeno.hostos.windows import send_to_zeno


def test_build_frame_is_a_valid_chat_frame() -> None:
    frame = send_to_zeno.build_frame(r"C:\Users\krish\report.pdf")
    # It must survive the server's own inbound parser.
    parsed = parse_inbound(
        json.dumps(frame), max_bytes=100_000, max_chars=10_000, max_context_chars=10_000
    )
    assert parsed.type == "chat"
    assert r"C:\Users\krish\report.pdf" in parsed.text
    assert parsed.context == r"C:\Users\krish\report.pdf"


def test_build_frame_ids_are_distinct() -> None:
    a = send_to_zeno.build_frame("x")
    b = send_to_zeno.build_frame("x")
    assert a["id"] != b["id"]


def test_a_very_long_path_is_trimmed() -> None:
    frame = send_to_zeno.build_frame("C:\\" + "a" * 5000)
    assert len(frame["context"]) == send_to_zeno.MAX_PATH


def test_send_opens_the_socket_and_sends_one_frame() -> None:
    sent: list[str] = []
    seen: dict[str, str] = {}

    @contextmanager
    def fake_connect(url: str, token: str) -> Any:
        seen["url"] = url
        seen["token"] = token

        class Sock:
            def send(self, message: str) -> None:
                sent.append(message)

        yield Sock()

    send_to_zeno.send(
        "C:\\file.txt",
        url="ws://127.0.0.1:8765/v1/chat/ws",
        token="T",  # noqa: S106
        connect=fake_connect,
    )

    assert seen == {"url": "ws://127.0.0.1:8765/v1/chat/ws", "token": "T"}
    assert len(sent) == 1
    assert json.loads(sent[0])["context"] == "C:\\file.txt"


def test_main_with_no_argument_is_a_usage_error() -> None:
    assert send_to_zeno.main([]) == 2
