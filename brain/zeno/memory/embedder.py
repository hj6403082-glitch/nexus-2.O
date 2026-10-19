"""Text embeddings from a GGUF model through llama.cpp (no PyTorch)."""

import asyncio
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import llama_cpp

from zeno.inference.base import InferenceError, ModelLoadError, ModelNotFoundError


class LlamaEmbedder:
    """Mean-pooled, unit-length embeddings. Loads lazily on a dedicated thread."""

    def __init__(self, model_path: Path, *, threads: int | None = None) -> None:
        self._path = model_path
        self._threads = threads
        self._llama: llama_cpp.Llama | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zeno-embed")
        self._load_lock = asyncio.Lock()

    @property
    def dimension(self) -> int:
        if self._llama is None:
            raise InferenceError("The embedding model is not loaded yet.")
        return int(self._llama.n_embd())

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        llama = await self._load()
        loop = asyncio.get_running_loop()
        vectors = await loop.run_in_executor(
            self._executor, lambda: llama.embed(list(texts), normalize=True)
        )
        return [list(map(float, v)) for v in vectors]

    async def _load(self) -> llama_cpp.Llama:
        async with self._load_lock:
            if self._llama is not None:
                return self._llama
            if not self._path.is_file():
                raise ModelNotFoundError(f"Embedding model not found: {self._path}")
            loop = asyncio.get_running_loop()
            try:
                self._llama = await loop.run_in_executor(self._executor, self._open)
            except Exception as error:
                raise ModelLoadError(f"Could not load {self._path.name}: {error}") from error
            return self._llama

    def _open(self) -> llama_cpp.Llama:
        return llama_cpp.Llama(
            model_path=str(self._path),
            embedding=True,
            pooling_type=llama_cpp.LLAMA_POOLING_TYPE_MEAN,
            n_threads=self._threads,
            verbose=False,
        )

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
        if self._llama is not None:
            self._llama.close()
            self._llama = None
