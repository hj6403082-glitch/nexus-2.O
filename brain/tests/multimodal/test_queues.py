"""Queue bounds: every multimodal queue is bounded and overflows the documented way."""

import asyncio

from zeno.multimodal.queues import AudioChunk, MultimodalQueues, SpeechJob, VisionJob


def chunk(seq: int) -> AudioChunk:
    return AudioChunk(utterance_id="u1", seq=seq, pcm=b"\x00\x00" * 4)


async def test_default_bounds_match_the_blueprint() -> None:
    queues = MultimodalQueues.create()
    assert queues.vision.maxsize == 4
    assert queues.audio_in.maxsize == 256
    assert queues.audio_out.maxsize == 32


async def test_vision_queue_fails_fast_when_full() -> None:
    queues = MultimodalQueues.create(vision_size=2)
    loop = asyncio.get_running_loop()
    jobs = [VisionJob(None, "what is this?", loop.create_future()) for _ in range(3)]
    assert queues.offer_vision(jobs[0])
    assert queues.offer_vision(jobs[1])
    assert not queues.offer_vision(jobs[2])
    assert queues.vision.qsize() == 2
    assert queues.dropped_vision == 1


async def test_audio_in_drops_the_new_chunk_and_counts_it() -> None:
    queues = MultimodalQueues.create(audio_in_size=3)
    accepted = [queues.offer_audio(chunk(n)) for n in range(5)]
    assert accepted == [True, True, True, False, False]
    assert queues.dropped_audio == 2
    kept = [queues.audio_in.get_nowait().seq for _ in range(3)]
    assert kept == [0, 1, 2]  # the gap after 2 is what the worker detects


async def test_audio_out_drops_the_newest_request() -> None:
    queues = MultimodalQueues.create(audio_out_size=2)
    jobs = [SpeechJob(f"r{n}", f"Sentence {n}.", None) for n in range(3)]
    assert [queues.offer_speech(j) for j in jobs] == [True, True, False]
    assert queues.dropped_speech == 1
    assert queues.audio_out.get_nowait().text == "Sentence 0."


async def test_clear_speech_empties_the_out_queue() -> None:
    queues = MultimodalQueues.create()
    for n in range(5):
        queues.offer_speech(SpeechJob(f"r{n}", "Hello.", "t1"))
    assert queues.clear_speech() == 5
    assert queues.audio_out.empty()
