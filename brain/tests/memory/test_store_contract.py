"""The VectorStore contract, run against every implementation.

Passing here is what makes ChromaDB swappable: anything else (FAISS, SQLite) only
has to pass the same tests.
"""

import math

import pytest

from zeno.memory.base import MemoryRecord, MemoryStoreError, VectorStore
from zeno.memory.chroma_store import ChromaVectorStore, ephemeral_client


def rec(
    id: str,
    text: str = "",
    *,
    kind: str = "episode",
    source: str = "conversation",
    session: str = "",
    created_at: float = 100.0,
    importance: float = 0.5,
) -> MemoryRecord:
    return MemoryRecord(
        id=id,
        text=text or id,
        kind=kind,  # type: ignore[arg-type]
        source=source,
        session=session,
        created_at=created_at,
        importance=importance,
    )


def unit(*values: float) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


X, Y, XY = unit(1, 0, 0), unit(0, 1, 0), unit(1, 1, 0)


def test_a_new_store_is_empty(store: VectorStore) -> None:
    assert store.count() == 0
    assert store.all() == []
    assert store.query(X, limit=5) == []


def test_round_trips_every_field(store: VectorStore) -> None:
    record = rec(
        "a", "likes green", kind="fact", source="seed", session="s1", created_at=5.5, importance=0.9
    )
    store.add([record], [X])
    assert store.get(["a"]) == [record]
    assert store.all() == [record]
    assert store.count() == 1


def test_query_ranks_by_similarity(store: VectorStore) -> None:
    store.add([rec("x"), rec("y"), rec("xy")], [X, Y, XY])
    hits = store.query(X, limit=3)
    assert [h.record.id for h in hits] == ["x", "xy", "y"]
    assert hits[0].similarity == pytest.approx(1.0, abs=1e-4)
    assert hits[1].similarity == pytest.approx(math.sqrt(0.5), abs=1e-4)
    assert hits[2].similarity == pytest.approx(0.0, abs=1e-4)


def test_limit_caps_results_and_may_exceed_the_count(store: VectorStore) -> None:
    store.add([rec("x"), rec("y")], [X, Y])
    assert len(store.query(X, limit=1)) == 1
    assert len(store.query(X, limit=50)) == 2


def test_filters_by_kind_and_source(store: VectorStore) -> None:
    store.add(
        [
            rec("e1", kind="episode", source="conversation"),
            rec("e2", kind="episode", source="debug"),
            rec("f1", kind="fact", source="seed"),
        ],
        [X, X, X],
    )
    assert {h.record.id for h in store.query(X, limit=5, kind="fact")} == {"f1"}
    assert {h.record.id for h in store.query(X, limit=5, kind="episode")} == {"e1", "e2"}
    assert {h.record.id for h in store.query(X, limit=5, kind="episode", source="debug")} == {"e2"}
    assert store.query(X, limit=5, kind="fact", source="debug") == []
    assert {r.id for r in store.all(kind="episode")} == {"e1", "e2"}
    assert store.count(kind="fact") == 1


def test_adding_an_existing_id_replaces_it(store: VectorStore) -> None:
    store.add([rec("a", "old")], [X])
    store.add([rec("a", "new")], [Y])
    assert store.count() == 1
    assert store.get(["a"])[0].text == "new"
    assert store.query(Y, limit=1)[0].record.id == "a"


def test_get_skips_unknown_ids(store: VectorStore) -> None:
    store.add([rec("a")], [X])
    assert [r.id for r in store.get(["missing", "a"])] == ["a"]
    assert store.get([]) == []


def test_delete_and_clear(store: VectorStore) -> None:
    store.add([rec("a"), rec("b"), rec("c")], [X, Y, XY])
    store.delete(["a", "never-existed"])
    assert {r.id for r in store.all()} == {"b", "c"}
    store.clear()
    assert store.count() == 0
    store.add([rec("d")], [X])
    assert store.count() == 1


def test_rejects_mismatched_batches(store: VectorStore) -> None:
    with pytest.raises(ValueError):
        store.add([rec("a"), rec("b")], [X])


def test_rejects_a_different_embedding_dimension(store: VectorStore) -> None:
    store.add([rec("a")], [X])
    with pytest.raises(MemoryStoreError):
        store.add([rec("b")], [[1.0, 0.0]])
    with pytest.raises(MemoryStoreError):
        store.query([1.0, 0.0], limit=1)


def test_empty_add_is_a_no_op(store: VectorStore) -> None:
    store.add([], [])
    assert store.count() == 0


def test_chroma_collections_are_isolated() -> None:
    client = ephemeral_client()
    first, second = ChromaVectorStore(client, "iso-one"), ChromaVectorStore(client, "iso-two")
    try:
        first.add([rec("a")], [X])
        assert second.count() == 0
    finally:
        client.delete_collection("iso-one")
        client.delete_collection("iso-two")
