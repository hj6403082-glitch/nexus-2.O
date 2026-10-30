from typing import Literal

import pytest
from llama_cpp import LlamaGrammar
from pydantic import BaseModel, Field

from zeno.inference.base import ChatMessage, GenerationParams, StructuredOutputError
from zeno.inference.fake import ScriptedEngine
from zeno.inference.grammar import gbnf_for_model, gbnf_for_schema
from zeno.inference.structured import generate_json


class Inner(BaseModel):
    ok: bool


class Decision(BaseModel):
    answer: Literal["yes", "no"]
    inner: Inner
    note: str = Field(max_length=10)


ASK = [ChatMessage("user", "decide")]
VALID = '{"answer": "yes", "inner": {"ok": true}, "note": "fine"}'


def test_gbnf_for_schema_has_a_root_rule() -> None:
    grammar = gbnf_for_schema({"type": "object", "properties": {"a": {"type": "boolean"}}})
    assert "root ::=" in grammar


def test_gbnf_for_model_covers_nested_models_and_enums() -> None:
    grammar = gbnf_for_model(Decision)
    assert "root ::=" in grammar
    assert '\\"yes\\"' in grammar and '\\"no\\"' in grammar
    assert '\\"ok\\"' in grammar
    LlamaGrammar.from_string(grammar, verbose=False)


def test_gbnf_for_model_is_cached() -> None:
    assert gbnf_for_model(Decision) is gbnf_for_model(Decision)


async def test_generate_json_returns_a_validated_model() -> None:
    engine = ScriptedEngine([['{"answer": "yes", ', '"inner": {"ok": true}, "note": "fine"}']])
    result = await generate_json(engine, ASK, Decision)
    assert result == Decision(answer="yes", inner=Inner(ok=True), note="fine")


async def test_generate_json_constrains_the_engine_with_the_model_grammar() -> None:
    engine = ScriptedEngine([VALID])
    await generate_json(engine, ASK, Decision, GenerationParams(max_tokens=50, temperature=0.1))
    messages, params = engine.calls[0]
    assert messages == ASK
    assert params.grammar == gbnf_for_model(Decision)
    assert params.max_tokens == 50
    assert params.temperature == 0.1


async def test_generate_json_retries_after_invalid_output() -> None:
    # The grammar cannot express max_length, so validation can still fail.
    too_long = '{"answer": "no", "inner": {"ok": false}, "note": "far too long a note"}'
    engine = ScriptedEngine([too_long, VALID])
    result = await generate_json(engine, ASK, Decision, max_attempts=2)
    assert result.answer == "yes"
    assert len(engine.calls) == 2


async def test_generate_json_raises_with_the_raw_text_when_attempts_run_out() -> None:
    engine = ScriptedEngine(['{"answer": "maybe"', '{"answer": "maybe"'])
    with pytest.raises(StructuredOutputError) as caught:
        await generate_json(engine, ASK, Decision, max_attempts=2)
    assert caught.value.raw == '{"answer": "maybe"'
    assert len(engine.calls) == 2


async def test_generate_json_rejects_zero_attempts() -> None:
    with pytest.raises(ValueError):
        await generate_json(ScriptedEngine([]), ASK, Decision, max_attempts=0)


class Ordered(BaseModel):
    thought: str
    answer: str


def test_grammar_keeps_the_declared_field_order() -> None:
    # The ReAct loop relies on "thought" being generated before the action, so the
    # grammar must not reorder fields (e.g. alphabetically).
    grammar = gbnf_for_model(Ordered)
    root = next(line for line in grammar.splitlines() if line.startswith("root ::="))
    assert root.index("thought") < root.index("answer")


def test_grammar_strings_cannot_contain_raw_control_characters() -> None:
    # JSON forbids unescaped U+0000-U+001F in strings; a grammar that allows them
    # lets the model produce text that no JSON parser accepts.
    grammar = gbnf_for_model(Ordered)
    char = next(line for line in grammar.splitlines() if line.startswith("char ::="))
    assert "\\x00-\\x1F" in char
    LlamaGrammar.from_string(grammar, verbose=False)
