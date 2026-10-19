"""``python -m zeno.senses``: manage device tokens and run the senses server."""

import argparse
import sys
from collections.abc import Sequence

import uvicorn

from zeno.config import Settings
from zeno.senses.auth import DeviceAuth
from zeno.senses.server import create_app, server_config


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m zeno.senses")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="run the WebSocket server (127.0.0.1 only in v1)")
    commands.add_parser("list", help="list registered devices")
    for name, text in (
        ("register", "create or rotate a device token"),
        ("revoke", "remove a device"),
    ):
        commands.add_parser(name, help=text).add_argument("device")
    args = parser.parse_args(argv)

    settings = settings or Settings()
    auth = DeviceAuth(settings.devices_file)
    if args.command == "register":
        try:
            token = auth.register(args.device)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 2
        print(f"Token for {args.device} (shown once; put it on the device):")
        print(token)
    elif args.command == "revoke":
        return 0 if auth.revoke(args.device) else 1
    elif args.command == "list":
        print("\n".join(auth.devices()))
    else:
        uvicorn.Server(server_config(settings, create_app(settings, auth=auth))).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
