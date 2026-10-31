"""VoiceWorker: audio chunks -> STT -> AudioCommandReceived; speech requests -> TTS -> sink."""

import asyncio
import threading
from collections.abc import AsyncIterator, Callable

import pytest

from tests.multimodal.conftest import Recorder, eventually
from zeno.multimodal.fake import FakeAudioSink, FakeSttEngine, FakeTtsEngine
from zeno.multimodal.queues import AudioChunk, EndReason, MultimodalQueues
from zeno.multimodal.voice_worker import VoiceWorker
from zeno.senses.events import DeviceEvent, EventBus, EventKind
from zeno.senses.protocol import AudioCommandReceived, SpeechSynthesisRequested

FRAME = b"\x01\x00" * 1280  # 80 ms of 16 kHz int16


class Voice:
    def __init__(self, bus: EventBus, *, stt: FakeSttEngine | None = None, **options: float):
        self.bus = bus
        self.stt = stt or FakeSttEngine()
        self.tts = FakeTtsEngine()
        self.sink = FakeAudioSink()
        self.queues = MultimodalQueues.create()
        self.worker = VoiceWorker(
            self.queues,
            bus,
            stt_factory=lambda: self.stt,
            tts_factory=lambda: self.tts,
            sink=self.sink,
            **options,  # type: ignore[arg-type]
        )
        self.detach = self.worker.attach()

    def utterance(
        self, uid: str = "u1", frames: int = 5, reason: EndReason = "silence", skip: int = -1
    ) -> None:
        for seq in range(frames):
            if seq == skip:
                continue
            last = seq == frames - 1
            self.queues.offer_audio(
                AudioChunk(uid, seq, FRAME, final=last, end_reason=reason if last else None)
            )

    def say(self, text: str, **fields: object) -> None:
        self.bus.publish(SpeechSynthesisRequested(text=text, **fields).to_event())  # type: ignore[arg-type]


@pytest.fixture
async def voice(bus: EventBus) -> AsyncIterator[Voice]:
    v = Voice(bus)
    await v.worker.start()
    yield v
    await v.worker.stop()


async def test_a_finished_utterance_becomes_an_audio_command(
    voice: Voice, record: Callable[[EventKind], Recorder]
) -> None:
    seen = record("audio_command")
    voice.utterance(frames=5)
    await eventually(lambda: bool(seen.events))
    command = AudioCommandReceived.from_event(seen.events[0])
    assert command.text == "Test command"
    assert command.utterance_id == "u1"
    assert command.duration_s == pytest.approx(0.4)
    (pcm, rate) = voice.stt.calls[0]
    assert pcm == FRAME * 5
    assert rate == 16000
    assert voice.stt.thread != threading.get_ident()  # STT ran off the loop


async def test_a_sequence_gap_discards_the_utterance(
    voice: Voice, record: Callable[[EventKind], Recorder]
) -> None:
    seen = record("audio_command")
    voice.utterance("broken", frames=5, skip=2)
    voice.utterance("good", frames=3)
    await eventually(lambda: bool(seen.events))
    assert [AudioCommandReceived.from_event(e).utterance_id for e in seen.events] == ["good"]
    assert voice.worker.discarded == 1
    assert len(voice.stt.calls) == 1


@pytest.mark.parametrize("reason", ["no_speech", "stopped"])
async def test_utterances_without_a_command_are_dropped(voice: Voice, reason: EndReason) -> None:
    voice.utterance("quiet", frames=3, reason=reason)
    voice.utterance("next", frames=2)
    await eventually(lambda: len(voice.stt.calls) == 1)
    assert voice.worker.discarded == 1


async def test_over_long_utterances_are_discarded(bus: EventBus) -> None:
    v = Voice(bus, max_utterance_s=0.2)
    await v.worker.start()
    try:
        v.utterance("long", frames=5)
        v.utterance("short", frames=2)
        await eventually(lambda: len(v.stt.calls) == 1)
        assert v.stt.calls[0][0] == FRAME * 2
    finally:
        await v.worker.stop()


async def test_empty_transcripts_publish_nothing(
    bus: EventBus, record: Callable[[EventKind], Recorder]
) -> None:
    seen = record("audio_command")
    v = Voice(bus, stt=FakeSttEngine(text="   "))
    await v.worker.start()
    try:
        v.utterance()
        await eventually(lambda: len(v.stt.calls) == 1)
        await bus.drain()
        assert seen.events == []
    finally:
        await v.worker.stop()


async def test_speech_requests_are_spoken_in_order(voice: Voice) -> None:
    voice.say("First sentence.")
    voice.say("Second sentence.")
    await eventually(lambda: len(voice.sink.played) == 2)
    assert voice.tts.calls == ["First sentence.", "Second sentence."]
    assert voice.sink.thread != threading.get_ident()  # playback off the loop


async def test_barge_in_empties_the_queue_and_stops_the_sink(voice: Voice) -> None:
    voice.sink.block = True  # the first sentence "plays" until stopped
    interrupted: list[bool] = []
    voice.worker.on_interrupt(lambda: interrupted.append(True))
    for n in range(5):
        voice.say(f"Sentence {n}.", turn_id="t1")
    await eventually(lambda: voice.sink.playing)
    voice.say("Stop.", interrupt=True)
    await eventually(lambda: voice.sink.stopped)
    await eventually(lambda: "Stop." in voice.tts.calls)
    voice.sink.block = False
    await eventually(lambda: voice.queues.audio_out.empty())
    assert interrupted == [True]
    assert voice.tts.calls == ["Sentence 0.", "Stop."]  # 1-4 were dropped


async def test_a_wake_word_interrupts_speech(voice: Voice) -> None:
    voice.sink.block = True
    voice.say("A long answer.")
    await eventually(lambda: voice.sink.playing)
    voice.bus.publish(
        DeviceEvent(device="microphone", kind="wake", data={"model": "hey_zeno"}, received_at=0)
    )
    await eventually(lambda: voice.sink.stopped)
    assert voice.worker.interrupts == 1


async def test_tts_failures_do_not_kill_the_worker(voice: Voice) -> None:
    voice.tts.fail = RuntimeError("voice model missing")
    voice.say("This fails.")
    await eventually(lambda: voice.worker.failed == 1)
    voice.tts.fail = None
    voice.say("This works.")
    await eventually(lambda: len(voice.sink.played) == 1)


async def test_stop_is_clean_and_idempotent(bus: EventBus) -> None:
    v = Voice(bus)
    await v.worker.start()
    v.utterance()
    await eventually(lambda: len(v.stt.calls) == 1)
    await v.worker.stop()
    await v.worker.stop()
    v.detach()
    await eventually(lambda: v.stt.closed)
    assert not v.tts.closed  # never used, so never loaded (engines load lazily)


async def test_stop_while_a_sentence_is_playing(bus: EventBus) -> None:
    v = Voice(bus)
    v.sink.block = True
    await v.worker.start()
    v.say("Playing.")
    await eventually(lambda: v.sink.playing)
    await asyncio.wait_for(v.worker.stop(), 2)
    assert v.sink.stopped
