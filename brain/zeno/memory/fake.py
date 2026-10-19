"""Dependency-free memory backends: a pure-Python vector store and a hashing embedder.

Both are real, deterministic implementations of the contracts, used by tests and
handy for running the brain without an embedding model.
"""

import hashlib
import math
import re
import threading
from collections.abc import Sequence

from zeno.memory.base import Kind, MemoryRecord, MemoryStoreError, ScoredRecord

_WORD = re.compile(r"[a-z0-9]+")


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = math.fsum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(math.fsum(x * x for x in a)) * math.sqrt(math.fsum(y * y for y in b))
    return dot / norm if norm else 0.0


class InMemoryVectorStore:
    """Brute-force cosine search over a dict. Fine for thousands of records."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[MemoryRecord, list[float]]] = {}
        self._dimension: int | None = None
        self._lock = threading.Lock()

    def add(self, records: Sequence[MemoryRecord], embeddings: Sequence[Sequence[float]]) -> None:
        if len(records) != len(embeddings):
            raise ValueError("records and embeddings must have the same length")
        with self._lock:
            for record, vector in zip(records, embeddings, strict=True):
                self._check_dimension(vector)
                self._items[record.id] = (record, list(vector))

    def get(self, ids: Sequence[str]) -> list[MemoryRecord]:
        with self._lock:
            return [self._items[i][0] for i in ids if i in self._items]

    def query(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
        kind: Kind | None = None,
        source: str | None = None,
    ) -> list[ScoredRecord]:
        with self._lock:
            if not self._items:
                return []
            self._check_dimension(embedding)
            hits = []
            for record, vector in self._items.values():
                if _matches(record, kind, source):
                    similarity = _cosine(embedding, vector)
                    hits.append(ScoredRecord(record, similarity, similarity))
        hits.sort(key=lambda h: h.similarity, reverse=True)
        return hits[:limit]

    def all(self, *, kind: Kind | None = None) -> list[MemoryRecord]:
        with self._lock:
            return [r for r, _ in self._items.values() if _matches(r, kind, None)]

    def count(self, *, kind: Kind | None = None) -> int:
        return len(self.all(kind=kind))

    def delete(self, ids: Sequence[str]) -> None:
        with self._lock:
            for i in ids:
                self._items.pop(i, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._dimension = None

    def _check_dimension(self, vector: Sequence[float]) -> None:
        if self._dimension is None:
            self._dimension = len(vector)
        elif len(vector) != self._dimension:
            raise MemoryStoreError(
                f"Embedding has {len(vector)} dimensions; this store holds {self._dimension}."
            )


def _matches(record: MemoryRecord, kind: Kind | None, source: str | None) -> bool:
    return (kind is None or record.kind == kind) and (source is None or record.source == source)


class HashEmbedder:
    """Signed feature hashing of lower-cased words: texts that share words score higher."""

    def __init__(self, dimension: int = 256) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        for word in _WORD.findall(text.lower()):
            digest = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest(), "big")
            vector[digest % self._dimension] += 1.0 if (digest >> 63) & 1 else -1.0
        norm = math.sqrt(math.fsum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector
