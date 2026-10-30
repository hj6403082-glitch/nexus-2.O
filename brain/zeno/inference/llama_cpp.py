"""Native inference on GGUF models through llama-cpp-python.

``LlamaCppEngine`` owns the async side: lazy loading, one generation at a time,
a bounded wait queue, cancellation and error mapping. All llama.cpp calls run on a
single dedicated worker thread, so the model is never touched concurrently and the
event loop never blocks. ``LlamaBackend`` is the thin adapter over ``llama_cpp.Llama``;
tests swap it for a fake through the ``loader`` argument.
"""

import asyncio
import threading
from collections.abc import AsyncGenerator, Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

import llama_cpp
from llama_cpp.llama_grammar import LlamaGrammar

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


class Backend(Protocol):
    """The synchronous model operations the engine needs."""

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop: list[str],
        seed: int | None,
        grammar: str | None,
    ) -> Iterator[str]: ...

    def tokenize(self, text: str) -> list[int]: ...

    def n_ctx(self) -> int: ...

    def validate_grammar(self, gbnf: str) -> bool: ...


BackendLoader = Callable[[Settings], Backend]


class LlamaBackend:
    """Adapter over ``llama_cpp.Llama``."""

    def __init__(self, settings: Settings) -> None:
        self._llama = llama_cpp.Llama(
            model_path=str(settings.model_path),
            n_ctx=settings.context_size,
            n_gpu_layers=settings.gpu_layers,
            n_threads=settings.threads,
            n_batch=settings.batch_size,
            verbose=False,
        )

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop: list[str],
        seed: int | None,
        grammar: str | None,
    ) -> Iterator[str]:
        chunks = self._llama.create_chat_completion(
            messages=messages,  # type: ignore[arg-type]  # TypedDicts at runtime
            stream=True,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
            seed=seed,
            grammar=LlamaGrammar.from_string(grammar, verbose=False) if grammar else None,
        )
        for chunk in chunks:
            delta: Any = chunk["choices"][0]["delta"]  # type: ignore[index]
            text = delta.get("content")
            if text:
                yield text

    def tokenize(self, text: str) -> list[int]:
        return self._llama.tokenize(text.encode("utf-8"), add_bos=False, special=False)

    def n_ctx(self) -> int:
        return self._llama.n_ctx()

    def validate_grammar(self, gbnf: str) -> bool:
        # llama.cpp crashes the process when sampling with an unparsable grammar,
        # so parse it against this model's vocabulary first. There is no public
        # wrapper for this; _model.vocab is what Llama itself passes.
        sampler = llama_cpp.llama_sampler_init_grammar(
            self._llama._model.vocab, gbnf.encode("utf-8"), b"root"
        )
        if not sampler:
            return False
        llama_cpp.llama_sampler_free(sampler)
        return True

    def close(self) -> None:
        self._llama.close()


def load_llama_backend(settings: Settings) -> Backend:
    return LlamaBackend(settings)


@dataclass(frozen=True, slots=True)
class _Failure:
    error: BaseException


_END = object()


class LlamaCppEngine:
    """``InferenceEngine`` backed by llama.cpp."""

    def __init__(self, settings: Settings, *, loader: BackendLoader = load_llama_backend) -> None:
        self._settings = settings
        self._loader = loader
        self._backend: Backend | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zeno-llama")
        self._load_lock = asyncio.Lock()
        self._gen_lock = asyncio.Lock()
        self._queued = 0
        self._closed = False

    @property
    def is_loaded(self) -> bool:
        return self._backend is not None

    @property
    def queued(self) -> int:
        """Requests waiting for the current generation to finish."""
        return self._queued

    @property
    def context_size(self) -> int:
        return self._backend.n_ctx() if self._backend else self._settings.context_size

    def count_tokens(self, text: str) -> int:
        if self._backend is None:
            raise InferenceError("The model is not loaded yet.")
        return len(self._backend.tokenize(text))

    def default_params(self) -> GenerationParams:
        s = self._settings
        return GenerationParams(
            max_tokens=s.max_tokens, temperature=s.temperature, top_p=s.top_p, seed=s.seed
        )

    async def load(self) -> None:
        """Load the model if needed. Safe to call repeatedly and concurrently."""
        self._ensure_open()
        async with self._load_lock:
            if self._backend is not None:
                return
            path = self._settings.model_path
            if path is None:
                raise ModelNotFoundError(
                    "No model configured. Set ZENO_MODEL_PATH to a .gguf file."
                )
            if not path.is_file():
                raise ModelNotFoundError(f"Model file not found: {path}")
            loop = asyncio.get_running_loop()
            try:
                self._backend = await loop.run_in_executor(
                    self._executor, self._loader, self._settings
                )
            except Exception as error:
                raise ModelLoadError(f"Could not load the model {path.name}: {error}") from error

    async def stream(
        self, messages: Sequence[ChatMessage], params: GenerationParams | None = None
    ) -> AsyncGenerator[str, None]:
        params = params or self.default_params()
        await self.load()
        backend = self._backend
        assert backend is not None  # noqa: S101  # load() guarantees it
        if self._gen_lock.locked() and self._queued >= self._settings.max_queue:
            raise EngineBusyError("Zeno is busy with other requests. Try again shortly.")
        self._queued += 1
        try:
            await self._gen_lock.acquire()
        finally:
            self._queued -= 1

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[object] = asyncio.Queue()
        stop = threading.Event()

        def emit(item: object) -> None:
            with suppress(RuntimeError):  # the loop may already be closed
                loop.call_soon_threadsafe(queue.put_nowait, item)

        def work() -> None:
            try:
                if params.grammar is not None and not backend.validate_grammar(params.grammar):
                    raise GrammarError("The output grammar is invalid.")
                chunks = backend.stream_chat(
                    [{"role": m.role, "content": m.content} for m in messages],
                    max_tokens=params.max_tokens,
                    temperature=params.temperature,
                    top_p=params.top_p,
                    stop=list(params.stop),
                    seed=params.seed,
                    grammar=params.grammar,
                )
                try:
                    for text in chunks:
                        if stop.is_set():
                            break
                        if text:
                            emit(text)
                finally:
                    close = getattr(chunks, "close", None)
                    if close is not None:
                        close()
            except BaseException as error:
                emit(_Failure(error))
            else:
                emit(_END)

        try:
            future = loop.run_in_executor(self._executor, work)
        except RuntimeError as error:  # executor shut down by close()
            self._gen_lock.release()
            raise InferenceError("The inference engine is closed.") from error
        # Release only once the worker has really finished, even if we are cancelled.
        future.add_done_callback(lambda _: self._gen_lock.release())
        try:
            while True:
                item = await queue.get()
                if item is _END:
                    return
                if isinstance(item, _Failure):
                    if isinstance(item.error, InferenceError):
                        raise item.error
                    raise InferenceError(f"The model failed while generating: {item.error}") from (
                        item.error
                    )
                assert isinstance(item, str)  # noqa: S101
                yield item
        finally:
            stop.set()

    def close(self) -> None:
        """Stop accepting work and free the model. Idempotent."""
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=True)
        close = getattr(self._backend, "close", None)
        if close is not None:
            close()
        self._backend = None

    def _ensure_open(self) -> None:
        if self._closed:
            raise InferenceError("The inference engine is closed.")
