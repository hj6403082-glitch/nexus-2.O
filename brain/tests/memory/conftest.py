import uuid
from collections.abc import Iterator

import pytest

from zeno.memory.base import VectorStore
from zeno.memory.chroma_store import ChromaVectorStore, ephemeral_client
from zeno.memory.fake import HashEmbedder, InMemoryVectorStore


@pytest.fixture
def embedder() -> HashEmbedder:
    return HashEmbedder()


@pytest.fixture
def chroma_store() -> Iterator[ChromaVectorStore]:
    # Ephemeral clients share one in-process database, so every test gets its own
    # collection and drops it afterwards.
    client = ephemeral_client()
    name = f"test-{uuid.uuid4().hex}"
    yield ChromaVectorStore(client, name)
    client.delete_collection(name)


@pytest.fixture(params=["in-memory", "chroma"])
def store(request: pytest.FixtureRequest) -> VectorStore:
    """Every VectorStore implementation, so one contract covers them all."""
    if request.param == "in-memory":
        return InMemoryVectorStore()
    chroma: VectorStore = request.getfixturevalue("chroma_store")
    return chroma


class Clock:
    """A settable clock for recency tests."""

    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()
