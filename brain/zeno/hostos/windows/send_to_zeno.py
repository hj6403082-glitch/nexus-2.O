"""The windowless client behind the "Send to Zeno" menu entry.

Explorer runs ``pythonw -m zeno.hostos.windows.send_to_zeno "<path>"``. This reads
the local API token, opens Zeno's loopback chat WebSocket, sends one message naming
the path, and exits. It opens no window and prints nothing unless run from a console.
The connection is injected, so the frame it sends is tested without a live server.
"""

import sys
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from zeno.api.auth import load_or_create_token
from zeno.config import Settings

MAX_PATH = 500


class Socket(Protocol):
    def send(self, message: str) -> None: ...


Connect = Callable[[str, str], AbstractContextManager[Socket]]


def brain_root() -> Path:
    # .../brain/zeno/hostos/windows/send_to_zeno.py -> .../brain
    return Path(__file__).resolve().parents[3]


def build_frame(path: str) -> dict[str, str]:
    """A chat frame that hands Zeno the clicked path. Its id is distinct per send."""
    import uuid

    trimmed = path[:MAX_PATH]
    return {
        "type": "chat",
        "id": f"shell-{uuid.uuid4().hex[:16]}",
        "text": f"I sent this from the Explorer right-click menu: {trimmed}",
        "context": trimmed,
    }


def send(path: str, *, url: str, token: str, connect: Connect) -> None:
    frame = build_frame(path)
    import json

    with connect(url, token) as socket:
        socket.send(json.dumps(frame))


def _default_connect(url: str, token: str) -> AbstractContextManager[Socket]:
    from websockets.sync.client import connect

    return connect(url, additional_headers={"Authorization": f"Bearer {token}"})


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print('usage: python -m zeno.hostos.windows.send_to_zeno "<path>"')
        return 2
    root = brain_root()
    settings = Settings(_env_file=root / ".env")
    token = load_or_create_token(root / settings.api_token_file)
    url = f"ws://{settings.senses_host}:{settings.senses_port}/v1/chat/ws"
    try:
        send(args[0], url=url, token=token, connect=_default_connect)
    except Exception:  # a windowless client must never pop an error dialog
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
