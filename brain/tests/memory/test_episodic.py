import pytest

from tests.memory.conftest import Clock
from zeno.memory.base import VectorStore
from zeno.memory.episodic import EpisodicMemory
from zeno.memory.fake import HashEmbedder

DAY = 86_400.0


@pytest.fixture
def episodes(store: VectorStore, embedder: HashEmbedder, clock: Clock) -> EpisodicMemory:
    return EpisodicMemory(store, embedder, clock=clock, half_life_days=30)


async def test_recall_on_an_empty_store_returns_nothing(episodes: EpisodicMemory) -> None:
    assert await episodes.recall("anything at all") == []


async def test_records_and_recalls_by_similarity(episodes: EpisodicMemory) -> None:
    await episodes.record("Boss asked about the football scores")
    await episodes.record("We talked about the green colour theme")
    hits = await episodes.recall("what did we say about the colour theme", min_similarity=0.1)
    assert hits[0].record.text == "We talked about the green colour theme"
    assert hits[0].record.kind == "episode"


async def test_threshold_filters_out_weak_matches(episodes: EpisodicMemory) -> None:
    await episodes.record("stock prices fell today")
    assert await episodes.recall("bake a chocolate cake", min_similarity=0.5) == []


async def test_similarity_is_reported_and_the_threshold_is_inclusive(
    episodes: EpisodicMemory,
) -> None:
    await episodes.record("exact same words")
    (hit,) = await episodes.recall("exact same words", min_similarity=1.0 - 1e-4)
    assert hit.similarity == pytest.approx(1.0, abs=1e-4)


async def test_recent_memories_outrank_old_ones_with_equal_similarity(
    episodes: EpisodicMemory, clock: Clock
) -> None:
    await episodes.record("planned the trip to the mountains")
    clock.now += 90 * DAY
    await episodes.record("planned the trip to the mountains again")
    hits = await episodes.recall("planned the trip to the mountains", min_similarity=0.1)
    assert hits[0].record.text.endswith("again")
    assert hits[0].score > hits[1].score


async def test_importance_breaks_ties(episodes: EpisodicMemory) -> None:
    await episodes.record("meeting notes alpha", importance=0.1)
    await episodes.record("meeting notes alpha", importance=0.9)
    hits = await episodes.recall("meeting notes alpha", min_similarity=0.1)
    assert [h.record.importance for h in hits] == [0.9, 0.1]


async def test_limit_and_source_filter(episodes: EpisodicMemory) -> None:
    for i in range(5):
        await episodes.record(f"chat about engines number {i}")
    await episodes.record("engine crashed with a traceback", source="debug", session="s9")
    assert len(await episodes.recall("engines", limit=2, min_similarity=0.0)) == 2
    debug = await episodes.recall("engines", source="debug", min_similarity=0.0)
    assert [h.record.text for h in debug] == ["engine crashed with a traceback"]
    assert debug[0].record.session == "s9"


async def test_blank_queries_return_nothing(episodes: EpisodicMemory) -> None:
    await episodes.record("something")
    assert await episodes.recall("   ") == []


@pytest.mark.parametrize("text", ["", "   "])
async def test_rejects_blank_episodes(episodes: EpisodicMemory, text: str) -> None:
    with pytest.raises(ValueError):
        await episodes.record(text)


@pytest.mark.parametrize("importance", [-0.1, 1.1])
async def test_rejects_importance_outside_zero_to_one(
    episodes: EpisodicMemory, importance: float
) -> None:
    with pytest.raises(ValueError):
        await episodes.record("x", importance=importance)


async def test_rejects_a_non_positive_limit(episodes: EpisodicMemory) -> None:
    with pytest.raises(ValueError):
        await episodes.recall("x", limit=0)


async def test_forget_and_count(episodes: EpisodicMemory) -> None:
    kept = await episodes.record("keep this")
    dropped = await episodes.record("drop this")
    assert await episodes.forget(dropped.id) is True
    assert await episodes.forget("unknown") is False
    assert [r.id for r in await episodes.all()] == [kept.id]
