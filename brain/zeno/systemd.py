"""Tell systemd how Zeno is doing (sd_notify), with no dependency.

Under ``Type=notify`` systemd hands the service a datagram socket in
``$NOTIFY_SOCKET``. Zeno writes ``READY=1`` once every pillar is up, ``WATCHDOG=1``
while its event loop is alive, and ``STOPPING=1`` on the way down. Without the
variable (Windows, a plain terminal) every call does nothing.
"""

import logging
import os
import socket
from collections.abc import Mapping

log = logging.getLogger(__name__)


class SystemdNotifier:
    def __init__(self, address: str | None = None, *, env: Mapping[str, str] | None = None) -> None:
        self._address = address
        self._env = env if env is not None else os.environ

    @classmethod
    def from_environment(cls) -> "SystemdNotifier":
        return cls(os.environ.get("NOTIFY_SOCKET"))

    @property
    def enabled(self) -> bool:
        return bool(self._address) and hasattr(socket, "AF_UNIX")

    def ready(self, status: str = "") -> bool:
        return self._send("READY=1", status)

    def status(self, text: str) -> bool:
        return self._send(None, text)

    def watchdog(self) -> bool:
        return self._send("WATCHDOG=1", "")

    def stopping(self) -> bool:
        return self._send("STOPPING=1", "")

    def watchdog_interval(self) -> float | None:
        """Seconds systemd waits for a ping, when the watchdog is meant for this process."""
        if not self.enabled:
            return None
        pid = self._env.get("WATCHDOG_PID")
        if pid is not None and pid != str(os.getpid()):
            return None
        try:
            usec = int(self._env.get("WATCHDOG_USEC", "0"))
        except ValueError:
            return None
        return usec / 1_000_000 if usec > 0 else None

    def _send(self, field: str | None, status: str) -> bool:
        if not self.enabled or self._address is None:
            return False
        lines = [field] if field else []
        if status:
            lines.append("STATUS=" + " ".join(status.split()))
        address = self._address
        if address.startswith("@"):  # Linux abstract socket namespace
            address = "\0" + address[1:]
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                sock.sendto("\n".join(lines).encode(), address)
        except OSError as error:
            log.debug("sd_notify failed: %s", error)
            return False
        return True
