"""Semantic memory: durable facts about the owner, seeded from their profile."""

import asyncio
import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from zeno.memory.base import Embedder, MemoryRecord, ScoredRecord, VectorStore


class ProfileError(Exception):
    pass


class OwnerProfile(BaseModel):
    """``zeno-profile.json``, the same file the web app reads."""

    name: str | None = None
    facts: list[str] = []


class FactMemory:
    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        *,
        clock: Callable[[], float] = time.time,
        duplicate_similarity: float = 0.95,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._clock = clock
        self._duplicate = duplicate_similarity

    async def remember(self, fact: str, *, source: str = "owner") -> MemoryRecord:
        """Store a fact, or return the existing one if it is a near-duplicate."""
        fact = fact.strip()
        if not fact:
            raise ValueError("a fact needs text")
        (vector,) = await self._embedder.embed([fact])
        nearest = await asyncio.to_thread(self._store.query, vector, limit=1, kind="fact")
        if nearest and nearest[0].similarity >= self._duplicate:
            return nearest[0].record
        record = MemoryRecord(
            id=uuid.uuid4().hex,
            text=fact,
            kind="fact",
            created_at=self._clock(),
            importance=1.0,
            source=source,
        )
        await asyncio.to_thread(self._store.add, [record], [vector])
        return record

    async def relevant(
        self, query: str, *, limit: int = 5, min_similarity: float = 0.35
    ) -> list[ScoredRecord]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if not query.strip():
            return []
        (vector,) = await self._embedder.embed([query])
        hits = await asyncio.to_thread(self._store.query, vector, limit=limit, kind="fact")
        return [h for h in hits if h.similarity >= min_similarity]

    async def all(self) -> list[MemoryRecord]:
        records = await asyncio.to_thread(self._store.all, kind="fact")
        return sorted(records, key=lambda r: r.created_at)

    async def forget(self, record_id: str) -> bool:
        found = await asyncio.to_thread(self._store.get, [record_id])
        if not found or found[0].kind != "fact":
            return False
        await asyncio.to_thread(self._store.delete, [record_id])
        return True

    async def forget_all(self) -> None:
        ids = [r.id for r in await self.all()]
        await asyncio.to_thread(self._store.delete, ids)

    async def seed_from_profile(self, path: Path) -> int:
        """Load the owner's profile as facts. Returns how many were new."""
        profile = await asyncio.to_thread(_read_profile, path)
        if profile is None:
            return 0
        name = (profile.name or "").strip()
        texts = [f"The owner's name is {name}."] if name else []
        texts += [f for f in profile.facts if f.strip()]
        known = {r.id for r in await self.all()}
        added = 0
        for text in texts:
            record = await self.remember(text, source="seed")
            if record.id not in known:
                known.add(record.id)
                added += 1
        return added


def _read_profile(path: Path) -> OwnerProfile | None:
    if not path.is_file():
        return None
    try:
        # utf-8-sig: Windows editors often save JSON with a byte-order mark.
        return OwnerProfile.model_validate(json.loads(path.read_text(encoding="utf-8-sig")))
    except (json.JSONDecodeError, ValidationError) as error:
        raise ProfileError(f"{path.name} is not a valid Zeno profile: {error}") from error
