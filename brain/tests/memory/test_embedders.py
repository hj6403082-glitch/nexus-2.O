import math
from collections.abc import Sequence
from pathlib import Path

import pytest

from tests.fixtures.tiny_gguf import write_tiny_gguf
from zeno.inference.base import ModelNotFoundError
from zeno.memory.base import Embedder
from zeno.memory.embedder import LlamaEmbedder
from zeno.memory.fake import HashEmbedder


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_hash_embedder_is_deterministic_and_normalised() -> None:
    embedder: Embedder = HashEmbedder(dimension=32)
    first, again = (
        await embedder.embed(["green user interface"]),
        await embedder.embed(["green user interface"]),
    )
    assert first == again
    assert len(first[0]) == embedder.dimension == 32
    assert math.fsum(v * v for v in first[0]) == pytest.approx(1.0)


async def test_hash_embedder_scores_shared_words_higher() -> None:
    a, b, c = await HashEmbedder().embed(
        ["Boss likes the green theme", "the green theme is liked", "stock prices fell today"]
    )
    assert cosine(a, b) > cosine(a, c)


async def test_hash_embedder_handles_blank_text() -> None:
    (vector,) = await HashEmbedder(dimension=8).embed(["   "])
    assert vector == [0.0] * 8


@pytest.fixture(scope="module")
def tiny_model(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_tiny_gguf(tmp_path_factory.mktemp("embed") / "tiny.gguf")


async def test_llama_embedder_on_a_real_gguf(tiny_model: Path) -> None:
    embedder = LlamaEmbedder(tiny_model)
    try:
        vectors = await embedder.embed(["hello world", "hello world", "something else"])
        assert embedder.dimension == 64
        assert all(len(v) == 64 for v in vectors)
        assert all(math.fsum(x * x for x in v) == pytest.approx(1.0, abs=1e-4) for v in vectors)
        assert vectors[0] == pytest.approx(vectors[1])
        assert await embedder.embed([]) == []
    finally:
        embedder.close()


async def test_llama_embedder_reports_a_missing_model(tmp_path: Path) -> None:
    embedder = LlamaEmbedder(tmp_path / "absent.gguf")
    with pytest.raises(ModelNotFoundError):
        await embedder.embed(["x"])
    embedder.close()
