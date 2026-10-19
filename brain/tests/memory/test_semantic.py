import json
from pathlib import Path

import pytest

from tests.memory.conftest import Clock
from zeno.memory.base import VectorStore
from zeno.memory.chroma_store import open_persistent_store
from zeno.memory.fake import HashEmbedder
from zeno.memory.semantic import FactMemory, ProfileError


@pytest.fixture
def facts(store: VectorStore, embedder: HashEmbedder, clock: Clock) -> FactMemory:
    return FactMemory(store, embedder, clock=clock)


async def test_remembers_and_lists_facts_oldest_first(facts: FactMemory, clock: Clock) -> None:
    await facts.remember("Boss studies computer science")
    clock.now += 10
    await facts.remember("Boss loves photography", source="conversation")
    listed = await facts.all()
    assert [f.text for f in listed] == ["Boss studies computer science", "Boss loves photography"]
    assert [f.source for f in listed] == ["owner", "conversation"]
    assert all(f.kind == "fact" for f in listed)


async def test_near_duplicates_are_not_stored_twice(facts: FactMemory) -> None:
    first = await facts.remember("Boss loves photography")
    again = await facts.remember("boss LOVES photography!")
    assert again.id == first.id
    assert len(await facts.all()) == 1


async def test_relevant_facts_respect_the_threshold(facts: FactMemory) -> None:
    await facts.remember("Boss prefers a green user interface")
    await facts.remember("Boss is 20 years old")
    hits = await facts.relevant("which colour interface does Boss like", min_similarity=0.2)
    assert hits[0].record.text == "Boss prefers a green user interface"
    assert await facts.relevant("quantum chromodynamics lecture", min_similarity=0.6) == []


async def test_relevant_on_an_empty_store(facts: FactMemory) -> None:
    assert await facts.relevant("anything") == []


async def test_forget_one_and_forget_all(facts: FactMemory) -> None:
    a = await facts.remember("fact one about cats")
    await facts.remember("fact two about dogs")
    assert await facts.forget(a.id) is True
    assert [f.text for f in await facts.all()] == ["fact two about dogs"]
    await facts.forget_all()
    assert await facts.all() == []


async def test_forget_all_leaves_episodes_alone(
    store: VectorStore, embedder: HashEmbedder, clock: Clock
) -> None:
    from zeno.memory.episodic import EpisodicMemory

    facts = FactMemory(store, embedder, clock=clock)
    episodes = EpisodicMemory(store, embedder, clock=clock)
    await facts.remember("a fact")
    await episodes.record("an episode")
    await facts.forget_all()
    assert [e.text for e in await episodes.all()] == ["an episode"]


async def test_seeds_from_the_owner_profile(facts: FactMemory, tmp_path: Path) -> None:
    profile = tmp_path / "zeno-profile.json"
    profile.write_text(
        "﻿"  # Windows editors often save JSON with a BOM
        + json.dumps({"name": "Boss", "facts": ["I love photography", "I am 20 years old"]}),
        encoding="utf-8",
    )
    assert await facts.seed_from_profile(profile) == 3
    texts = {f.text for f in await facts.all()}
    assert texts == {"The owner's name is Boss.", "I love photography", "I am 20 years old"}
    assert {f.source for f in await facts.all()} == {"seed"}
    # Seeding again adds nothing.
    assert await facts.seed_from_profile(profile) == 0
    assert len(await facts.all()) == 3


async def test_blank_names_and_repeated_facts_are_not_counted(
    facts: FactMemory, tmp_path: Path
) -> None:
    profile = tmp_path / "zeno-profile.json"
    profile.write_text(json.dumps({"name": "  ", "facts": ["I cook", "I cook", " "]}))
    assert await facts.seed_from_profile(profile) == 1
    assert [f.text for f in await facts.all()] == ["I cook"]


async def test_a_missing_profile_seeds_nothing(facts: FactMemory, tmp_path: Path) -> None:
    assert await facts.seed_from_profile(tmp_path / "absent.json") == 0


@pytest.mark.parametrize("content", ["{not json", '{"facts": "not a list"}', "[]"])
async def test_a_malformed_profile_is_an_error(
    facts: FactMemory, tmp_path: Path, content: str
) -> None:
    profile = tmp_path / "zeno-profile.json"
    profile.write_text(content, encoding="utf-8")
    with pytest.raises(ProfileError):
        await facts.seed_from_profile(profile)


async def test_facts_persist_across_restarts(tmp_path: Path, embedder: HashEmbedder) -> None:
    path = tmp_path / "memory"
    first = FactMemory(open_persistent_store(path), embedder)
    await first.remember("Boss lives with two cats")
    del first

    reopened = FactMemory(open_persistent_store(path), embedder)
    assert [f.text for f in await reopened.all()] == ["Boss lives with two cats"]
    hits = await reopened.relevant("how many cats", min_similarity=0.1)
    assert hits[0].record.text == "Boss lives with two cats"
