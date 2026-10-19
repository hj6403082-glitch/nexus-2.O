"""Episodic memory: past conversations and debug logs, recalled by similarity."""

import asyncio
import time
import uuid
from collections.abc import Callable

from zeno.memory.base import Embedder, MemoryRecord, ScoredRecord, VectorStore

DAY = 86_400.0


class EpisodicMemory:
    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        *,
        clock: Callable[[], float] = time.time,
        half_life_days: float = 30.0,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._clock = clock
        self._half_life = half_life_days * DAY

    async def record(
        self,
        text: str,
        *,
        source: str = "conversation",
        session: str = "",
        importance: float = 0.5,
    ) -> MemoryRecord:
        text = text.strip()
        if not text:
            raise ValueError("an episode needs text")
        if not 0.0 <= importance <= 1.0:
            raise ValueError("importance must be between 0 and 1")
        record = MemoryRecord(
            id=uuid.uuid4().hex,
            text=text,
            kind="episode",
            created_at=self._clock(),
            importance=importance,
            source=source,
            session=session,
        )
        (vector,) = await self._embedder.embed([text])
        await asyncio.to_thread(self._store.add, [record], [vector])
        return record

    async def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        min_similarity: float = 0.35,
        source: str | None = None,
    ) -> list[ScoredRecord]:
        """Most useful episodes: similar enough, then ranked by recency and importance."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if not query.strip():
            return []
        (vector,) = await self._embedder.embed([query])
        candidates = await asyncio.to_thread(
            self._store.query, vector, limit=max(limit * 4, 20), kind="episode", source=source
        )
        now = self._clock()
        ranked = [
            ScoredRecord(hit.record, hit.similarity, self._score(hit, now))
            for hit in candidates
            if hit.similarity >= min_similarity
        ]
        ranked.sort(key=lambda h: h.score, reverse=True)
        return ranked[:limit]

    def _score(self, hit: ScoredRecord, now: float) -> float:
        # Recency and importance scale the score down to half at most, so a strong
        # old memory still beats a weak new one.
        age = max(0.0, now - hit.record.created_at)
        recency: float = 0.5 ** (age / self._half_life)
        return hit.similarity * (0.5 + 0.5 * recency) * (0.5 + 0.5 * hit.record.importance)

    async def all(self) -> list[MemoryRecord]:
        records = await asyncio.to_thread(self._store.all, kind="episode")
        return sorted(records, key=lambda r: r.created_at)

    async def forget(self, record_id: str) -> bool:
        found = await asyncio.to_thread(self._store.get, [record_id])
        if not found or found[0].kind != "episode":
            return False
        await asyncio.to_thread(self._store.delete, [record_id])
        return True

    async def forget_all(self) -> None:
        ids = [r.id for r in await self.all()]
        await asyncio.to_thread(self._store.delete, ids)
