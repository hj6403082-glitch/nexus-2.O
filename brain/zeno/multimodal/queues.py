"""The data plane: bounded queues between the EventBus side and the workers.

Items are plain frozen dataclasses: they carry bytes and futures, which are internal,
not a boundary. Every ``offer_*`` is non-blocking and never raises; a full queue is
counted and handled the way ZENO_MULTIMODAL_ARCH.md section 3 says.
"""

import asyncio
from dataclasses import dataclass
from typing import Literal, TypeVar

EndReason = Literal["silence", "max_length", "no_speech", "stopped"]
"""Why an utterance ended. Only ``silence`` and ``max_length`` hold a command."""

SAMPLE_RATE = 16000


@dataclass(frozen=True, slots=True)
class VisionJob:
    frame_id: str | None
    """None: the newest frame in the store."""
    question: str
    future: "asyncio.Future[str]"


@dataclass(frozen=True, slots=True)
class AudioChunk:
    utterance_id: str
    seq: int
    pcm: bytes
    """16 kHz mono int16."""
    final: bool = False
    end_reason: EndReason | None = None


@dataclass(frozen=True, slots=True)
class SpeechJob:
    request_id: str
    text: str
    turn_id: str | None


T = TypeVar("T")


@dataclass
class MultimodalQueues:
    vision: "asyncio.Queue[VisionJob]"
    audio_in: "asyncio.Queue[AudioChunk]"
    audio_out: "asyncio.Queue[SpeechJob]"
    dropped_vision: int = 0
    dropped_audio: int = 0
    dropped_speech: int = 0

    @classmethod
    def create(
        cls, *, vision_size: int = 4, audio_in_size: int = 256, audio_out_size: int = 32
    ) -> "MultimodalQueues":
        for size in (vision_size, audio_in_size, audio_out_size):
            if size < 1:
                raise ValueError("Multimodal queues must be bounded (size >= 1).")
        return cls(
            asyncio.Queue(vision_size), asyncio.Queue(audio_in_size), asyncio.Queue(audio_out_size)
        )

    def offer_vision(self, job: VisionJob) -> bool:
        """Queue a vision job, or return False at once if vision is busy (fail fast)."""
        if _offer(self.vision, job):
            return True
        self.dropped_vision += 1
        return False

    def offer_audio(self, chunk: AudioChunk) -> bool:
        """Queue a microphone chunk. When full the chunk is dropped; the voice worker sees
        the sequence gap and discards that utterance. Must run on the loop thread."""
        if _offer(self.audio_in, chunk):
            return True
        self.dropped_audio += 1
        return False

    def offer_speech(self, job: SpeechJob) -> bool:
        """Queue a sentence to speak; when full the newest request is dropped."""
        if _offer(self.audio_out, job):
            return True
        self.dropped_speech += 1
        return False

    def clear_speech(self) -> int:
        """Drop everything waiting to be spoken (barge-in). Returns how many."""
        cleared = 0
        while True:
            try:
                self.audio_out.get_nowait()
            except asyncio.QueueEmpty:
                return cleared
            self.audio_out.task_done()
            cleared += 1


def _offer(queue: "asyncio.Queue[T]", item: T) -> bool:
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        return False
    return True
