"""VoiceWorker: speech to text from audio_in_queue, text to speech from audio_out_queue.

Two background tasks, each with its own engine thread, so listening and speaking never
wait on each other; playback has a third thread. Bus handlers here only enqueue or
flip flags, never await real work, so the EventBus dispatcher is never held up.
"""

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from zeno.multimodal.base import Audio, AudioSink, SttEngine, Transcript, TtsEngine
from zeno.multimodal.queues import SAMPLE_RATE, AudioChunk, MultimodalQueues, SpeechJob
from zeno.multimodal.workers import EngineSlot, cancel_task, next_item
from zeno.senses.events import DeviceEvent, EventBus
from zeno.senses.protocol import AudioCommandReceived, SpeechSynthesisRequested

log = logging.getLogger(__name__)

COMMAND_ENDS = {"silence", "max_length"}


@dataclass
class _Utterance:
    id: str
    next_seq: int = 0
    parts: list[bytes] = field(default_factory=list)
    size: int = 0
    broken: bool = False


class VoiceWorker:
    def __init__(
        self,
        queues: MultimodalQueues,
        bus: EventBus,
        *,
        stt_factory: Callable[[], SttEngine],
        tts_factory: Callable[[], TtsEngine],
        sink: AudioSink,
        sample_rate: int = SAMPLE_RATE,
        max_utterance_s: float = 15.0,
        idle_unload: float = 600.0,
    ) -> None:
        self._queues = queues
        self._bus = bus
        self._stt: EngineSlot[SttEngine] = EngineSlot("stt", stt_factory, idle_unload=idle_unload)
        self._tts: EngineSlot[TtsEngine] = EngineSlot("tts", tts_factory, idle_unload=idle_unload)
        self._sink = sink
        self._player = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zeno-speaker")
        self._rate = sample_rate
        # A little slack over the listener's own cap, which cuts at max_utterance_s.
        self._max_bytes = int(max_utterance_s * sample_rate * 2 * 1.1)
        self._utterance: _Utterance | None = None
        self._generation = 0
        self._interrupt_callbacks: list[Callable[[], object]] = []
        self._tasks: list[asyncio.Task[None]] = []
        self.transcribed = 0
        self.discarded = 0
        self.spoken = 0
        self.failed = 0
        self.interrupts = 0

    # -- bus side: only enqueue or flip flags ------------------------------------------

    def attach(self) -> Callable[[], None]:
        """Listen for speech requests and wake words. Returns an unsubscribe function."""
        off_speech = self._bus.subscribe(self._on_speech_request, kind="speech_request")
        off_wake = self._bus.subscribe(self._on_wake, kind="wake")

        def detach() -> None:
            off_speech()
            off_wake()

        return detach

    def on_interrupt(self, callback: Callable[[], object]) -> None:
        """Run ``callback`` on every barge-in (the voice turn handler cancels its turn)."""
        self._interrupt_callbacks.append(callback)

    async def _on_speech_request(self, event: DeviceEvent) -> None:
        request = SpeechSynthesisRequested.from_event(event)
        if request.interrupt:
            self.interrupt()
        if not self._queues.offer_speech(
            SpeechJob(request.request_id, request.text, request.turn_id)
        ):
            log.warning("Speech queue full; dropped: %.40s", request.text)

    async def _on_wake(self, event: DeviceEvent) -> None:
        # The owner is about to speak: stop talking over them.
        self.interrupt()

    def interrupt(self) -> None:
        """Barge-in: drop queued speech, cut the current clip, tell listeners."""
        self.interrupts += 1
        self._generation += 1
        self._queues.clear_speech()
        try:
            self._sink.stop()
        except Exception:
            log.exception("Stopping playback failed")
        for callback in list(self._interrupt_callbacks):
            try:
                callback()
            except Exception:
                log.exception("Interrupt callback failed")

    # -- lifecycle -----------------------------------------------------------------------

    async def start(self) -> None:
        if not self._tasks:
            self._tasks = [
                asyncio.create_task(self._stt_loop(), name="zeno-voice-stt"),
                asyncio.create_task(self._tts_loop(), name="zeno-voice-tts"),
            ]

    async def stop(self) -> None:
        """Stop both loops, cut playback, close the engines. Idempotent."""
        tasks, self._tasks = self._tasks, []
        if not tasks:
            return
        self._generation += 1
        self._sink.stop()
        for task in tasks:
            await cancel_task(task)
        self._player.shutdown(wait=False, cancel_futures=True)
        await self._stt.shutdown()
        await self._tts.shutdown()

    # -- speech to text --------------------------------------------------------------------

    async def _stt_loop(self) -> None:
        queue = self._queues.audio_in
        while True:
            chunk = await next_item(queue, self._stt.idle_unload, self._stt.unload)
            try:
                pcm = self._assemble(chunk)
                if pcm is not None:
                    await self._transcribe(chunk.utterance_id, pcm)
            finally:
                queue.task_done()

    def _assemble(self, chunk: AudioChunk) -> bytes | None:
        """Add a chunk to the utterance; return the whole utterance when it is complete
        and worth transcribing."""
        current = self._utterance
        if current is None or current.id != chunk.utterance_id:
            if current is not None:  # the previous one never got its final chunk
                self.discarded += 1
            current = self._utterance = _Utterance(chunk.utterance_id)
        if chunk.seq != current.next_seq:
            current.broken = True  # a dropped chunk: half a command is worse than none
        current.next_seq = chunk.seq + 1
        current.parts.append(chunk.pcm)
        current.size += len(chunk.pcm)
        if current.size > self._max_bytes:
            current.broken = True
        if not chunk.final:
            return None
        self._utterance = None
        if current.broken or chunk.end_reason not in COMMAND_ENDS or not current.size:
            self.discarded += 1
            return None
        return b"".join(current.parts)

    async def _transcribe(self, utterance_id: str, pcm: bytes) -> None:
        rate = self._rate
        try:
            transcript: Transcript = await self._stt.run(
                lambda: self._stt.engine().transcribe(pcm, rate)
            )
        except Exception:
            self.failed += 1
            log.exception("Speech to text failed")
            return
        text = transcript.text.strip()[:2000]
        if not text:
            return
        self.transcribed += 1
        command = AudioCommandReceived(
            utterance_id=utterance_id,
            text=text,
            language=transcript.language[:16] or "en",
            confidence=min(max(transcript.confidence, 0.0), 1.0),
            duration_s=len(pcm) / (2 * rate),
        )
        self._bus.publish(command.to_event())

    # -- text to speech --------------------------------------------------------------------

    async def _tts_loop(self) -> None:
        queue = self._queues.audio_out
        while True:
            job = await next_item(queue, self._tts.idle_unload, self._tts.unload)
            try:
                await self._speak(job)
            finally:
                queue.task_done()

    async def _speak(self, job: SpeechJob) -> None:
        generation = self._generation
        try:
            audio: Audio = await self._tts.run(lambda: self._tts.engine().synthesize(job.text))
        except Exception:
            self.failed += 1
            log.exception("Text to speech failed")
            return
        if generation != self._generation:  # interrupted while synthesising
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(self._player, self._sink.play, audio)
        except Exception:
            self.failed += 1
            log.exception("Playback failed")
            return
        self.spoken += 1
