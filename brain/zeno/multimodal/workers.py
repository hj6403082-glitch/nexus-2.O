"""Shared plumbing for queue workers: a lazily loaded engine on its own thread."""

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Generic, Protocol, TypeVar

log = logging.getLogger(__name__)


class Closable(Protocol):
    def close(self) -> None: ...


E = TypeVar("E", bound=Closable)
T = TypeVar("T")


class EngineSlot(Generic[E]):
    """Owns one native engine and the single thread it runs on.

    The engine is built on first use (on the thread, since loading a model blocks) and
    closed after ``idle_unload`` seconds without work, freeing its RAM.
    """

    def __init__(self, name: str, factory: Callable[[], E], *, idle_unload: float) -> None:
        self.name = name
        self._factory = factory
        self.idle_unload = idle_unload
        self._engine: E | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"zeno-{name}")

    @property
    def loaded(self) -> bool:
        return self._engine is not None

    def engine(self) -> E:
        """The engine, loading it if needed. Call only on this slot's thread."""
        if self._engine is None:
            log.info("Loading the %s engine", self.name)
            self._engine = self._factory()
        return self._engine

    async def run(self, func: Callable[[], T]) -> T:
        """Run ``func`` on this slot's thread and await its result."""
        return await asyncio.get_running_loop().run_in_executor(self._executor, func)

    async def unload(self) -> None:
        if self._engine is not None:
            await self.run(self._close)

    def _close(self) -> None:
        engine, self._engine = self._engine, None
        if engine is not None:
            try:
                engine.close()
            except Exception:
                log.exception("Closing the %s engine failed", self.name)
            log.info("Unloaded the %s engine", self.name)

    async def shutdown(self) -> None:
        """Close the engine on its thread (after any running job), then stop the thread."""
        try:
            await self.unload()
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)


async def next_item(queue: "asyncio.Queue[T]", idle: float, on_idle: Callable[[], object]) -> T:
    """Wait for the next queue item; after ``idle`` seconds of nothing, run ``on_idle``
    (an engine unload) once and keep waiting."""
    try:
        return await asyncio.wait_for(queue.get(), idle)
    except TimeoutError:
        result = on_idle()
        if asyncio.iscoroutine(result):
            await result
        return await queue.get()


async def cancel_task(task: "asyncio.Task[None] | None") -> None:
    if task is None or task.done():
        return
    task.cancel()
    await asyncio.wait([task])
