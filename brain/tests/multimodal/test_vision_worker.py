"""VisionWorker: drains vision_queue, runs the VLM on its own thread, answers futures."""

import asyncio
import io
import threading
from collections.abc import AsyncIterator

import pytest
from PIL import Image

from tests.multimodal.conftest import eventually, png
from zeno.multimodal.fake import FakeVisionEngine
from zeno.multimodal.frames import FrameNotFoundError, FrameStore
from zeno.multimodal.queues import MultimodalQueues, VisionJob
from zeno.multimodal.vision_worker import ImageRejectedError, VisionWorker


class Setup:
    def __init__(self, engine: FakeVisionEngine, **options: float) -> None:
        self.engine = engine
        self.queues = MultimodalQueues.create()
        self.store = FrameStore(None)
        self.worker = VisionWorker(self.queues, self.store, lambda: engine, **options)  # type: ignore[arg-type]

    def ask(
        self, question: str = "What is this?", frame_id: str | None = None
    ) -> asyncio.Future[str]:
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        assert self.queues.offer_vision(VisionJob(frame_id, question, future))
        return future


@pytest.fixture
async def setup() -> AsyncIterator[Setup]:
    s = Setup(FakeVisionEngine())
    await s.worker.start()
    yield s
    await s.worker.stop()


async def test_answers_with_the_engine_result(setup: Setup) -> None:
    frame = setup.store.put(png(), source="upload")
    answer = await asyncio.wait_for(setup.ask(frame_id=frame.id), 2)
    assert answer == "I see a test image"
    (image, mime, question, _max_tokens) = setup.engine.calls[0]
    assert mime == "image/jpeg"  # re-encoded after the size check
    assert question == "What is this?"
    assert Image.open(io.BytesIO(image)).format == "JPEG"
    assert setup.worker.processed == 1


async def test_newest_frame_by_default(setup: Setup) -> None:
    setup.store.put(png(color="red"), source="a")
    setup.store.put(png(40, 30, color="green"), source="b")
    await asyncio.wait_for(setup.ask(), 2)
    image = Image.open(io.BytesIO(setup.engine.calls[0][0]))
    assert image.size == (40, 30)


async def test_missing_frame_fails_the_future(setup: Setup) -> None:
    with pytest.raises(FrameNotFoundError):
        await asyncio.wait_for(setup.ask(frame_id="gone"), 2)
    assert setup.worker.failed == 1


async def test_engine_errors_reach_the_caller() -> None:
    s = Setup(FakeVisionEngine(fail=RuntimeError("model crashed")))
    await s.worker.start()
    try:
        s.store.put(png(), source="upload")
        with pytest.raises(RuntimeError, match="model crashed"):
            await asyncio.wait_for(s.ask(), 2)
        # The worker survives and serves the next job.
        s.engine.fail = None
        assert await asyncio.wait_for(s.ask(), 2) == "I see a test image"
    finally:
        await s.worker.stop()


async def test_big_images_are_downscaled() -> None:
    s = Setup(FakeVisionEngine(), max_side=64)
    await s.worker.start()
    try:
        s.store.put(png(400, 200), source="upload")
        await asyncio.wait_for(s.ask(), 2)
        assert Image.open(io.BytesIO(s.engine.calls[0][0])).size == (64, 32)
    finally:
        await s.worker.stop()


async def test_decompression_bombs_are_refused() -> None:
    s = Setup(FakeVisionEngine(), max_pixels=1000)
    await s.worker.start()
    try:
        s.store.put(png(100, 100), source="upload")
        with pytest.raises(ImageRejectedError, match="too many pixels"):
            await asyncio.wait_for(s.ask(), 2)
        assert s.engine.calls == []
    finally:
        await s.worker.stop()


async def test_the_model_never_runs_on_the_event_loop() -> None:
    """A slow fake VLM plus a 20 ms ticker: the loop keeps ticking while it works."""
    engine = FakeVisionEngine(delay=0.4)
    s = Setup(engine)
    await s.worker.start()
    ticks = 0
    worst = 0.0

    async def ticker() -> None:
        nonlocal ticks, worst
        loop = asyncio.get_running_loop()
        while True:
            before = loop.time()
            await asyncio.sleep(0.02)
            worst = max(worst, loop.time() - before)
            ticks += 1

    probe = asyncio.create_task(ticker())
    try:
        s.store.put(png(), source="upload")
        await asyncio.wait_for(s.ask(), 3)
        assert engine.thread != threading.get_ident()
        assert ticks >= 10
        assert worst < 0.15
    finally:
        probe.cancel()
        await s.worker.stop()


async def test_the_engine_loads_lazily_and_unloads_when_idle() -> None:
    engine = FakeVisionEngine()
    loads = 0

    def factory() -> FakeVisionEngine:
        nonlocal loads
        loads += 1
        return engine

    queues = MultimodalQueues.create()
    store = FrameStore(None)
    worker = VisionWorker(queues, store, factory, idle_unload=0.05)
    await worker.start()
    try:
        assert loads == 0
        store.put(png(), source="upload")
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        queues.offer_vision(VisionJob(None, "q", future))
        await asyncio.wait_for(future, 2)
        assert loads == 1
        await eventually(lambda: engine.closed)
    finally:
        await worker.stop()


async def test_a_job_whose_caller_gave_up_is_skipped(setup: Setup) -> None:
    setup.store.put(png(), source="upload")
    future = setup.ask()
    future.cancel()
    done = setup.ask()
    assert await asyncio.wait_for(done, 2) == "I see a test image"
    assert len(setup.engine.calls) == 1


async def test_stop_fails_pending_jobs_and_closes_the_engine() -> None:
    engine = FakeVisionEngine(delay=0.3)
    s = Setup(engine)
    await s.worker.start()
    s.store.put(png(), source="upload")
    first = s.ask()
    waiting = s.ask()
    await eventually(lambda: engine.started > 0)
    await s.worker.stop()
    for future in (first, waiting):
        assert future.done()
        assert future.cancelled() or isinstance(future.exception(), RuntimeError)
    await eventually(lambda: engine.closed)
