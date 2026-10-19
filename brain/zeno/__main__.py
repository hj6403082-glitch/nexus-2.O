"""``python -m zeno``: run the brain (default), or print the chat API token."""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence

from zeno.api.auth import load_or_create_token
from zeno.config import Settings
from zeno.daemon import ZenoDaemon


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

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    daemon = ZenoDaemon(settings)
    asyncio.run(daemon.serve())
    if daemon.state == "failed":
        print(f"Zeno could not start: {daemon.error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
