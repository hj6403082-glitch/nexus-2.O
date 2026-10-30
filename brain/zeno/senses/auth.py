"""Per-device bearer tokens. Only SHA-256 hashes are kept, in memory and on disk."""

import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path

DEVICE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_bearer(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    token = token.strip()
    return token if scheme.lower() == "bearer" and token else None


class DeviceAuth:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._hashes: dict[str, str] = {}
        if path is not None and path.is_file():
            self._hashes = {str(k): str(v) for k, v in json.loads(path.read_text()).items()}

    def register(self, device: str) -> str:
        """Create (or rotate) a device's token and return it. It is shown only once."""
        if not DEVICE_ID.fullmatch(device):
            raise ValueError("device ids are 2-48 lowercase letters, digits or dashes")
        token = secrets.token_urlsafe(32)
        self._hashes[device] = _hash(token)
        self._save()
        return token

    def verify(self, device: str, token: str) -> bool:
        expected = self._hashes.get(device)
        # Compare even for unknown devices so timing does not reveal which exist.
        ok = hmac.compare_digest(expected or "", _hash(token))
        return bool(token) and expected is not None and ok

    def revoke(self, device: str) -> bool:
        if self._hashes.pop(device, None) is None:
            return False
        self._save()
        return True

    def devices(self) -> list[str]:
        return sorted(self._hashes)

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._hashes, indent=2, sort_keys=True))
        os.chmod(temp, 0o600)
        temp.replace(self._path)
