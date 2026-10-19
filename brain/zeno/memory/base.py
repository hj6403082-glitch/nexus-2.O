"""Memory contracts. Everything above the store depends on these, never on ChromaDB."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Kind = Literal["episode", "fact"]


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: str
    text: str
    kind: Kind
    created_at: float
    """Unix time."""
    importance: float = 0.5
    """0 to 1."""
    source: str = ""
    """Where it came from: conversation, debug, seed, owner, …"""
    session: str = ""


@dataclass(frozen=True, slots=True)
class ScoredRecord:
    record: MemoryRecord
    similarity: float
    """Cosine similarity to the query, -1 to 1."""
    score: float
    """Ranking score after recency and importance (equals similarity when unranked)."""


class VectorStore(Protocol):
    """Persistent vectors plus their records. Implementations must pass
    ``tests/memory/test_store_contract.py``."""

    def add(self, records: Sequence[MemoryRecord], embeddings: Sequence[Sequence[float]]) -> None:
        """Insert or replace records by id."""
        ...

    def get(self, ids: Sequence[str]) -> list[MemoryRecord]:
        """Records for the ids that exist."""
        ...

    def query(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
        kind: Kind | None = None,
        source: str | None = None,
    ) -> list[ScoredRecord]:
        """Nearest records, most similar first."""
        ...

    def all(self, *, kind: Kind | None = None) -> list[MemoryRecord]: ...

    def count(self, *, kind: Kind | None = None) -> int: ...

    def delete(self, ids: Sequence[str]) -> None:
        """Remove records; unknown ids are ignored."""
        ...

    def clear(self) -> None: ...


class Embedder(Protocol):
    @property
    def dimension(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Unit-length vectors, one per text."""
        ...


class MemoryStoreError(Exception):
    """The vector store rejected an operation (e.g. a dimension mismatch)."""
