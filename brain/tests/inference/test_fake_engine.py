import pytest

from zeno.inference.base import ChatMessage, GenerationParams, InferenceEngine, InferenceError
from zeno.inference.fake import ScriptedEngine

HI = [ChatMessage("user", "hi")]


async def collect(engine: InferenceEngine, params: GenerationParams | None = None) -> list[str]:
    return [chunk async for chunk in engine.stream(HI, params)]


async def test_streams_scripted_chunks_and_records_calls() -> None:
    engine = ScriptedEngine([["Hel", "lo"], "Bye"])
    assert await collect(engine) == ["Hel", "lo"]
    assert await collect(engine, GenerationParams(max_tokens=5)) == ["Bye"]
    assert [params.max_tokens for _, params in engine.calls] == [
        GenerationParams().max_tokens,
        5,
    ]


async def test_raises_when_the_script_runs_out() -> None:
    with pytest.raises(InferenceError):
        await collect(ScriptedEngine([]))


def test_satisfies_the_engine_protocol() -> None:
    engine: InferenceEngine = ScriptedEngine([], context_size=128)
    assert engine.context_size == 128
    assert engine.count_tokens("three little words") == 3
