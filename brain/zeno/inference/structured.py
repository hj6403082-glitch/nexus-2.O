"""Grammar-constrained JSON generation validated into Pydantic models."""

from collections.abc import Sequence
from contextlib import aclosing
from dataclasses import replace
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from zeno.inference.base import (
    ChatMessage,
    GenerationParams,
    InferenceEngine,
    StructuredOutputError,
)
from zeno.inference.grammar import gbnf_for_model

T = TypeVar("T", bound=BaseModel)


async def generate_json(
    engine: InferenceEngine,
    messages: Sequence[ChatMessage],
    model: type[T],
    params: GenerationParams | None = None,
    *,
    max_attempts: int = 2,
) -> T:
    """Generate output that matches ``model``.

    The grammar guarantees well-formed JSON of the right shape; Pydantic then checks
    what a grammar cannot (lengths, ranges, a response cut off by ``max_tokens``).
    Invalid output is retried up to ``max_attempts`` times in total.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    constrained = replace(params or GenerationParams(), grammar=gbnf_for_model(model))
    raw = ""
    for _ in range(max_attempts):
        async with aclosing(engine.stream(messages, constrained)) as stream:
            raw = "".join([chunk async for chunk in stream])
        try:
            return model.model_validate_json(raw)
        except ValidationError:
            continue
    raise StructuredOutputError(
        f"The model did not produce valid {model.__name__} JSON after {max_attempts} attempts.",
        raw,
    )
