"""``python -m zeno``: run the brain (default), or print the chat API token."""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path

from zeno.api.auth import load_or_create_token
from zeno.config import Settings
from zeno.daemon import ZenoDaemon

LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def configure_logging(settings: Settings) -> Path | None:
    """Log to stderr; with no console (pythonw, as the Windows logon task runs Zeno), log
    to ``settings.log_file`` instead and return its path."""
    if sys.stderr is not None:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
        return None
    path = settings.log_file
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s " + LOG_FORMAT))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return path


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m zeno")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="run the brain on 127.0.0.1 (the default)")
    commands.add_parser("token", help="print the chat API token (created if missing)")
    args = parser.parse_args(argv)
    settings = settings or Settings()

    if args.command == "token":
        print(load_or_create_token(settings.api_token_file))
        return 0

    configure_logging(settings)
    daemon = ZenoDaemon(settings)
    try:
        asyncio.run(daemon.serve())
    except KeyboardInterrupt:  # Ctrl+C: the server has already shut down cleanly
        return 0
    if daemon.state == "failed":
        print(f"Zeno could not start: {daemon.error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
