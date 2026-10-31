"""VisionWorker: drains vision_queue and runs the VLM on its own thread.

Each job names a frame (or the newest) and a question. The worker fetches the bytes
from the FrameStore, checks and downscales the image with Pillow, and asks the engine,
all on the worker thread. The answer, or the error, lands in the job's future.
"""

import asyncio
import io
import logging
from collections.abc import Callable

from PIL import Image

from zeno.multimodal.base import MultimodalError, VisionEngine
from zeno.multimodal.frames import Frame, FrameStore
from zeno.multimodal.queues import MultimodalQueues, VisionJob
from zeno.multimodal.workers import EngineSlot, cancel_task, next_item

log = logging.getLogger(__name__)


class ImageRejectedError(MultimodalError):
    """The bytes are not an image the VLM may see (corrupt, wrong format, too big)."""


def prepare_image(data: bytes, *, max_side: int, max_pixels: int) -> bytes:
    """Decode with a pixel limit, verify JPEG/PNG, downscale, re-encode as JPEG.

    The size check reads only the header, so a decompression bomb is refused before
    any pixels are decoded."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise ImageRejectedError("Only JPEG or PNG images can be analysed.")
            width, height = image.size
            if width * height > max_pixels:
                raise ImageRejectedError(
                    f"The image has too many pixels ({width}x{height}); the limit is {max_pixels}."
                )
            image.load()
            rgb = image.convert("RGB")
    except ImageRejectedError:
        raise
    except Exception as error:  # Pillow raises many types for a corrupt file
        raise ImageRejectedError(f"The image could not be decoded: {error}") from error
    rgb.thumbnail((max_side, max_side))
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=90)
    return out.getvalue()


class VisionWorker:
    def __init__(
        self,
        queues: MultimodalQueues,
        store: FrameStore,
        engine_factory: Callable[[], VisionEngine],
        *,
        max_tokens: int = 200,
        max_side: int = 768,
        max_pixels: int = 40_000_000,
        idle_unload: float = 600.0,
    ) -> None:
        self._queue = queues.vision
        self._store = store
        self._slot: EngineSlot[VisionEngine] = EngineSlot(
            "vision", engine_factory, idle_unload=idle_unload
        )
        self._max_tokens = max_tokens
        self._max_side = max_side
        self._max_pixels = max_pixels
        self._task: asyncio.Task[None] | None = None
        self.processed = 0
        self.failed = 0

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="zeno-vision-worker")

    async def stop(self) -> None:
        """Stop taking jobs, fail the ones still waiting, close the engine. Idempotent."""
        task, self._task = self._task, None
        if task is None:
            return
        await cancel_task(task)
        while not self._queue.empty():
            job = self._queue.get_nowait()
            if not job.future.done():
                job.future.set_exception(RuntimeError("Vision is shutting down."))
        await self._slot.shutdown()

    async def _run(self) -> None:
        while True:
            job = await next_item(self._queue, self._slot.idle_unload, self._slot.unload)
            try:
                await self._process(job)
            except asyncio.CancelledError:
                if not job.future.done():
                    job.future.set_exception(RuntimeError("Vision is shutting down."))
                raise
            finally:
                self._queue.task_done()

    async def _process(self, job: VisionJob) -> None:
        if job.future.done():  # the caller gave up (tool timeout)
            return
        try:
            frame = self._store.get(job.frame_id)
            answer = await self._slot.run(lambda: self._analyze(frame, job.question))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.failed += 1
            log.warning("Vision job failed: %s", error)
            if not job.future.done():
                job.future.set_exception(error)
            return
        self.processed += 1
        if not job.future.done():
            job.future.set_result(answer)

    def _analyze(self, frame: Frame, question: str) -> str:
        """Runs on the vision thread."""
        image = prepare_image(frame.data, max_side=self._max_side, max_pixels=self._max_pixels)
        engine = self._slot.engine()
        return engine.describe(image, "image/jpeg", question, max_tokens=self._max_tokens)
