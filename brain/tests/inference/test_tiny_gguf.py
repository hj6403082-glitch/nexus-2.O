"""Integration: the real llama.cpp backend on a tiny generated GGUF.

The model's weights are random, so its text is gibberish; these tests check the
plumbing (loading, chat templating, streaming, tokenising, grammar enforcement,
cancellation) rather than answer quality.
"""

from collections.abc import AsyncIterator
from contextlib import aclosing
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from zeno.config import Settings
from zeno.inference.base import ChatMessage, GenerationParams, GrammarError, ModelLoadError
from zeno.inference.llama_cpp import LlamaCppEngine
from zeno.inference.structured import generate_json

HI = [ChatMessage("system", "You are Zeno."), ChatMessage("user", "hi")]


class Verdict(BaseModel):
    answer: Literal["yes", "no", "unsure"]
    confident: bool


@pytest.fixture
async def engine(tiny_gguf: Path) -> AsyncIterator[LlamaCppEngine]:
    engine = LlamaCppEngine(Settings(_env_file=None, model_path=tiny_gguf, context_size=512))
    yield engine
    engine.close()


async def test_loads_and_reports_model_facts(engine: LlamaCppEngine) -> None:
    await engine.load()
    assert engine.is_loaded
    assert engine.context_size == 512
    assert engine.count_tokens("hello world") > 0


async def test_streams_text(engine: LlamaCppEngine) -> None:
    chunks = [c async for c in engine.stream(HI, GenerationParams(max_tokens=12, seed=1))]
    assert all(isinstance(c, str) for c in chunks)
    assert len(chunks) >= 1


@pytest.mark.parametrize("seed", range(5))
async def test_grammar_forces_valid_json_from_a_random_model(
    engine: LlamaCppEngine, seed: int
) -> None:
    verdict = await generate_json(
        engine, HI, Verdict, GenerationParams(max_tokens=64, temperature=1.0, seed=seed)
    )
    assert isinstance(verdict, Verdict)


class Note(BaseModel):
    # Bounded so a random model always reaches the closing quote within max_tokens.
    title: str = Field(max_length=12)
    body: str = Field(max_length=24)


@pytest.mark.parametrize("seed", range(5))
async def test_grammar_forces_valid_free_text_strings(engine: LlamaCppEngine, seed: int) -> None:
    # Random weights pick odd bytes, control characters included; the grammar must
    # keep every string valid JSON.
    note = await generate_json(
        engine, HI, Note, GenerationParams(max_tokens=200, temperature=1.0, seed=seed)
    )
    assert isinstance(note, Note)


async def test_invalid_grammar_raises_instead_of_crashing(engine: LlamaCppEngine) -> None:
    # llama.cpp segfaults on an unparsable grammar, so the engine must refuse it.
    with pytest.raises(GrammarError):
        async with aclosing(engine.stream(HI, GenerationParams(grammar="garbage"))) as stream:
            async for _ in stream:
                pass
    chunks = [c async for c in engine.stream(HI, GenerationParams(max_tokens=4, seed=2))]
    assert chunks is not None


async def test_early_close_then_reuse(engine: LlamaCppEngine) -> None:
    async with aclosing(engine.stream(HI, GenerationParams(max_tokens=200, seed=3))) as stream:
        async for _ in stream:
            break
    again = [c async for c in engine.stream(HI, GenerationParams(max_tokens=4, seed=4))]
    assert again is not None


async def test_corrupt_model_file_is_a_load_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.gguf"
    bad.write_bytes(b"not a model")
    engine = LlamaCppEngine(Settings(_env_file=None, model_path=bad))
    with pytest.raises(ModelLoadError):
        await engine.load()
    engine.close()
