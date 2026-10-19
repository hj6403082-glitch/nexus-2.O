import pytest

from tests.memory.conftest import Clock
from zeno.inference.base import ChatMessage
from zeno.memory.base import VectorStore
from zeno.memory.episodic import EpisodicMemory
from zeno.memory.fake import HashEmbedder
from zeno.memory.manager import MemoryManager
from zeno.memory.semantic import FactMemory


@pytest.fixture
def manager(store: VectorStore, embedder: HashEmbedder, clock: Clock) -> MemoryManager:
    return MemoryManager(
        facts=FactMemory(store, embedder, clock=clock),
        episodes=EpisodicMemory(store, embedder, clock=clock),
        min_similarity=0.2,
    )


async def test_recall_lists_relevant_facts_before_episodes(manager: MemoryManager) -> None:
    await manager.facts.remember("Boss prefers the green theme")
    await manager.episodes.record("Yesterday we changed the theme to green")
    await manager.episodes.record("Talked about football results")
    recalled = await manager.recall("change the theme to green", limit=3)
    assert recalled[0] == "Boss prefers the green theme"
    assert "Yesterday we changed the theme to green" in recalled
    assert "Talked about football results" not in recalled


async def test_recall_on_empty_memory(manager: MemoryManager) -> None:
    assert await manager.recall("hello") == []


async def test_recall_respects_the_limit(manager: MemoryManager) -> None:
    for i in range(4):
        await manager.facts.remember(f"green fact number {i} about green")
        await manager.episodes.record(f"green episode number {i} about green")
    assert len(await manager.recall("green", limit=3)) == 3


async def test_archive_turns_evicted_messages_into_one_episode(manager: MemoryManager) -> None:
    evicted = [ChatMessage("user", "set a timer"), ChatMessage("assistant", "Timer set.")]
    record = await manager.archive(evicted, session="s1")
    assert record is not None
    assert record.text == "user: set a timer\nassistant: Timer set."
    assert record.session == "s1"
    assert await manager.archive([], session="s1") is None


async def test_wipe_forgets_everything(manager: MemoryManager) -> None:
    await manager.facts.remember("a fact")
    await manager.episodes.record("an episode")
    await manager.wipe()
    assert await manager.facts.all() == []
    assert await manager.episodes.all() == []
