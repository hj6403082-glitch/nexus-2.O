"""The chat socket's bearer token, kept in a file only the owner can read."""

import hmac
import os
import secrets
from pathlib import Path


def load_or_create_token(path: Path) -> str:
    """Read the token, creating it (mode 600) on first use."""
    if path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, f"{token}\n".encode())
    finally:
        os.close(fd)
    return token


def token_matches(given: str | None, expected: str) -> bool:
    if not given or not expected:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())
