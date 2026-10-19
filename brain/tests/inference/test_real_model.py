"""Opt-in checks against a real chat model: `ZENO_TEST_MODEL=path/to.gguf pytest -m slow`."""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel

from zeno.config import Settings
from zeno.inference.base import ChatMessage, GenerationParams
from zeno.inference.llama_cpp import LlamaCppEngine
from zeno.inference.structured import generate_json

pytestmark = pytest.mark.slow


class Arithmetic(BaseModel):
    result: int
    operation: Literal["add", "subtract", "multiply", "divide"]


@pytest.fixture(scope="module")
def model_path() -> Path:
    value = os.environ.get("ZENO_TEST_MODEL")
    if not value or not Path(value).is_file():
        pytest.skip("set ZENO_TEST_MODEL to a GGUF chat model to run these")
    return Path(value)


@pytest.fixture
async def engine(model_path: Path) -> AsyncIterator[LlamaCppEngine]:
    engine = LlamaCppEngine(Settings(model_path=model_path))
    yield engine
    engine.close()


async def test_answers_in_plain_text(engine: LlamaCppEngine) -> None:
    messages = [ChatMessage("user", "Reply with just the word: ready")]
    text = "".join([c async for c in engine.stream(messages, GenerationParams(max_tokens=16))])
    assert "ready" in text.lower()


async def test_structured_output_is_correct(engine: LlamaCppEngine) -> None:
    messages = [ChatMessage("user", "What is 6 times 7? Answer as JSON.")]
    answer = await generate_json(
        engine, messages, Arithmetic, GenerationParams(max_tokens=64, temperature=0.0)
    )
    assert answer == Arithmetic(result=42, operation="multiply")
