"""Append-only structured audit log of everything the agent thinks and does."""

import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

AuditKind = Literal[
    "run_started",
    "thought",
    "action",
    "refused",
    "approval_requested",
    "approval",
    "observation",
    "step_rejected",
    "aborted",
    "final",
    "run_finished",
]


@dataclass(frozen=True, slots=True)
class AuditRecord:
    ts: float
    run_id: str
    step: int
    kind: AuditKind
    data: Mapping[str, Any] = field(default_factory=dict)


class AuditError(Exception):
    """The audit log could not be written. The agent stops rather than act unrecorded."""


class AuditLog(Protocol):
    async def record(self, record: AuditRecord) -> None: ...


class MemoryAuditLog:
    """Keeps records in a list (tests and previews)."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    async def record(self, record: AuditRecord) -> None:
        self.records.append(record)


class JsonlAuditLog:
    """One JSON object per line, appended with ``O_APPEND`` and never rewritten.

    The class deliberately has no way to edit, truncate or delete entries.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._path

    async def record(self, record: AuditRecord) -> None:
        line = json.dumps(asdict(record), ensure_ascii=False, default=str) + "\n"
        async with self._lock:  # keeps lines in the order they were recorded
            try:
                await asyncio.to_thread(self._append, line.encode("utf-8"))
            except OSError as error:
                raise AuditError(f"Cannot write the audit log at {self._path}: {error}") from error

    def _append(self, data: bytes) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)


def read_audit(path: Path) -> list[AuditRecord]:
    """Parse a JSONL audit log (for the owner, tests and tooling)."""
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            raw = json.loads(line)
            records.append(
                AuditRecord(raw["ts"], raw["run_id"], raw["step"], raw["kind"], raw["data"])
            )
    return records
