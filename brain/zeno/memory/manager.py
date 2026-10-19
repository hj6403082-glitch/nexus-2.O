"""Joins the long-term tiers into what the prompt builder needs."""

from collections.abc import Sequence

from zeno.inference.base import ChatMessage
from zeno.memory.base import MemoryRecord
from zeno.memory.episodic import EpisodicMemory
from zeno.memory.semantic import FactMemory


class MemoryManager:
    def __init__(
        self, *, facts: FactMemory, episodes: EpisodicMemory, min_similarity: float = 0.35
    ) -> None:
        self.facts = facts
        self.episodes = episodes
        self._min_similarity = min_similarity

    async def recall(self, query: str, *, limit: int = 5) -> list[str]:
        """Memory lines for ``PromptBuilder``: relevant facts first, then episodes,
        most relevant first (the builder drops from the end when space is short)."""
        facts = await self.facts.relevant(query, limit=limit, min_similarity=self._min_similarity)
        episodes = await self.episodes.recall(
            query, limit=limit, min_similarity=self._min_similarity
        )
        return [h.record.text for h in (*facts, *episodes)][:limit]

    async def archive(
        self, messages: Sequence[ChatMessage], *, session: str
    ) -> MemoryRecord | None:
        """Store messages that left working memory as one episode."""
        if not messages:
            return None
        text = "\n".join(f"{m.role}: {m.content}" for m in messages)
        return await self.episodes.record(text, session=session)

    async def wipe(self) -> None:
        await self.facts.forget_all()
        await self.episodes.forget_all()
