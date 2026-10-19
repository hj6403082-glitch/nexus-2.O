"""LlamaCppEngine against a fake backend: threading, locking, errors, cancellation.

The real llama.cpp backend is exercised by test_tiny_gguf.py.
"""

import asyncio
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import aclosing
from pathlib import Path
from typing import Any

import pytest

from zeno.config import Settings
from zeno.inference.base import (
    ChatMessage,
    EngineBusyError,
    GenerationParams,
    GrammarError,
    InferenceError,
    ModelLoadError,
    ModelNotFoundError,
)
from zeno.inference.llama_cpp import LlamaCppEngine

HI = [ChatMessage("user", "hi")]


class FakeBackend:
    def __init__(
        self,
        chunks: Sequence[str] = ("Hel", "lo"),
        *,
        delay: float = 0.0,
        gate: threading.Event | None = None,
        fail_at: int | None = None,
        grammar_ok: bool = True,
    ) -> None:
        self.chunks = list(chunks)
        self.delay = delay
        self.gate = gate
        self.fail_at = fail_at
        self.grammar_ok = grammar_ok
        self.calls: list[tuple[list[dict[str, str]], dict[str, Any]]] = []
        self.pulled = 0
        self.active = 0
        self.max_active = 0
        self.closed = 0

    def stream_chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Iterator[str]:
        self.calls.append((messages, kwargs))
        return self._run()

    def _run(self) -> Iterator[str]:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            for i, chunk in enumerate(self.chunks):
                if self.gate is not None:
                    self.gate.wait(5)
                if i == self.fail_at:
                    raise RuntimeError("boom")
                time.sleep(self.delay)
                self.pulled += 1
                yield chunk
        finally:
            self.active -= 1
            self.closed += 1

    def tokenize(self, text: str) -> list[int]:
        return list(range(len(text.split())))

    def n_ctx(self) -> int:
        return 2048

    def validate_grammar(self, gbnf: str) -> bool:
        return self.grammar_ok


@pytest.fixture
def model_file(tmp_path: Path) -> Path:
    path = tmp_path / "model.gguf"
    path.write_bytes(b"GGUF")
    return path


def make_engine(
    model_file: Path, backend: FakeBackend, **overrides: Any
) -> tuple[LlamaCppEngine, list[Settings]]:
    loads: list[Settings] = []

    def loader(settings: Settings) -> FakeBackend:
        loads.append(settings)
        return backend

    settings = Settings(_env_file=None, model_path=model_file, **overrides)
    return LlamaCppEngine(settings, loader=loader), loads


async def collect(engine: LlamaCppEngine, params: GenerationParams | None = None) -> str:
    async with aclosing(engine.stream(HI, params)) as stream:
        return "".join([chunk async for chunk in stream])


async def wait_for(condition: Any, limit: float = 5.0) -> None:
    deadline = time.monotonic() + limit
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.005)


async def test_streams_backend_chunks_in_order(model_file: Path) -> None:
    engine, _ = make_engine(model_file, FakeBackend(["a", "", "b", "c"]))
    assert await collect(engine) == "abc"
    engine.close()


async def test_forwards_messages_and_generation_params(model_file: Path) -> None:
    backend = FakeBackend()
    engine, _ = make_engine(model_file, backend)
    params = GenerationParams(max_tokens=42, temperature=0.3, top_p=0.5, stop=("END",), seed=9)
    await collect(engine, params)
    messages, kwargs = backend.calls[0]
    assert messages == [{"role": "user", "content": "hi"}]
    assert kwargs == {
        "max_tokens": 42,
        "temperature": 0.3,
        "top_p": 0.5,
        "stop": ["END"],
        "seed": 9,
        "grammar": None,
    }


async def test_defaults_come_from_settings(model_file: Path) -> None:
    backend = FakeBackend()
    engine, _ = make_engine(model_file, backend, max_tokens=123, temperature=0.2, seed=7)
    await collect(engine)
    _, kwargs = backend.calls[0]
    assert (kwargs["max_tokens"], kwargs["temperature"], kwargs["seed"]) == (123, 0.2, 7)


async def test_loads_lazily_and_only_once(model_file: Path) -> None:
    engine, loads = make_engine(model_file, FakeBackend())
    assert not engine.is_loaded
    assert loads == []
    await asyncio.gather(collect(engine), collect(engine))
    await collect(engine)
    assert len(loads) == 1
    assert engine.is_loaded


async def test_explicit_load(model_file: Path) -> None:
    engine, loads = make_engine(model_file, FakeBackend())
    await engine.load()
    await engine.load()
    assert len(loads) == 1


async def test_missing_model_path_is_reported(tmp_path: Path) -> None:
    engine = LlamaCppEngine(Settings(_env_file=None), loader=lambda s: FakeBackend())
    with pytest.raises(ModelNotFoundError, match="ZENO_MODEL_PATH"):
        await engine.load()
    engine = LlamaCppEngine(
        Settings(_env_file=None, model_path=tmp_path / "absent.gguf"),
        loader=lambda s: FakeBackend(),
    )
    with pytest.raises(ModelNotFoundError, match=r"absent\.gguf"):
        await collect(engine)


async def test_loader_failures_become_model_load_errors_and_can_retry(model_file: Path) -> None:
    attempts: list[int] = []

    def flaky(settings: Settings) -> FakeBackend:
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("bad magic")
        return FakeBackend()

    engine = LlamaCppEngine(Settings(_env_file=None, model_path=model_file), loader=flaky)
    with pytest.raises(ModelLoadError) as caught:
        await engine.load()
    assert isinstance(caught.value.__cause__, ValueError)
    assert await collect(engine) == "Hello"


async def test_backend_errors_surface_and_the_engine_recovers(model_file: Path) -> None:
    backend = FakeBackend(["a", "b", "c"], fail_at=1)
    engine, _ = make_engine(model_file, backend)
    received: list[str] = []
    with pytest.raises(InferenceError) as caught:
        async with aclosing(engine.stream(HI)) as stream:
            async for chunk in stream:
                received.append(chunk)
    assert received == ["a"]
    assert isinstance(caught.value.__cause__, RuntimeError)
    backend.fail_at = None
    assert await collect(engine) == "abc"


async def test_invalid_grammar_is_rejected_before_sampling(model_file: Path) -> None:
    backend = FakeBackend(grammar_ok=False)
    engine, _ = make_engine(model_file, backend)
    with pytest.raises(GrammarError):
        await collect(engine, GenerationParams(grammar="root ::= nope"))
    assert backend.calls == []


async def test_valid_grammar_is_forwarded(model_file: Path) -> None:
    backend = FakeBackend()
    engine, _ = make_engine(model_file, backend)
    await collect(engine, GenerationParams(grammar='root ::= "x"'))
    assert backend.calls[0][1]["grammar"] == 'root ::= "x"'


async def test_closing_the_stream_early_stops_the_backend(model_file: Path) -> None:
    backend = FakeBackend([str(i) for i in range(200)], delay=0.002)
    engine, _ = make_engine(model_file, backend)
    async with aclosing(engine.stream(HI)) as stream:
        async for _ in stream:
            break
    await wait_for(lambda: backend.closed == 1)
    assert backend.pulled < 200
    backend.chunks = ["ok"]
    assert await collect(engine) == "ok"


async def test_cancelling_the_consumer_stops_the_backend(model_file: Path) -> None:
    backend = FakeBackend([str(i) for i in range(200)], delay=0.002)
    engine, _ = make_engine(model_file, backend)
    task = asyncio.create_task(collect(engine))
    await wait_for(lambda: backend.pulled > 0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await wait_for(lambda: backend.closed == 1)
    assert backend.pulled < 200
    backend.chunks = ["ok"]
    assert await collect(engine) == "ok"


async def test_generations_never_overlap(model_file: Path) -> None:
    backend = FakeBackend(["x"] * 5, delay=0.002)
    engine, _ = make_engine(model_file, backend)
    results = await asyncio.gather(*(collect(engine) for _ in range(3)))
    assert results == ["xxxxx"] * 3
    assert backend.max_active == 1


async def test_rejects_requests_beyond_the_queue_limit(model_file: Path) -> None:
    gate = threading.Event()
    backend = FakeBackend(["a"], gate=gate)
    engine, _ = make_engine(model_file, backend, max_queue=1)
    first = asyncio.create_task(collect(engine))
    await wait_for(lambda: backend.active == 1)
    second = asyncio.create_task(collect(engine))
    await wait_for(lambda: engine.queued == 1)
    with pytest.raises(EngineBusyError):
        await collect(engine)
    gate.set()
    assert await asyncio.gather(first, second) == ["a", "a"]
    assert engine.queued == 0


async def test_count_tokens_and_context_size(model_file: Path) -> None:
    engine, _ = make_engine(model_file, FakeBackend(), context_size=1024)
    assert engine.context_size == 1024
    with pytest.raises(InferenceError):
        engine.count_tokens("not loaded yet")
    await engine.load()
    assert engine.count_tokens("three little words") == 3
    assert engine.context_size == 2048


async def test_closed_engine_refuses_work(model_file: Path) -> None:
    engine, _ = make_engine(model_file, FakeBackend())
    engine.close()
    engine.close()
    with pytest.raises(InferenceError):
        await collect(engine)
