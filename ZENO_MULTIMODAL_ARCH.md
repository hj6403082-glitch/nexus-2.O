# Zeno multimodal layer: sight and voice without blocking the EventBus

**Status:** approved by Boss 2026-10-31 (all section 11 defaults). Built in `brain/zeno/multimodal/`; the real engines (`LlamaVisionEngine`, `FasterWhisperStt`, `PiperTts`, `SoundDeviceSink`) live together in `multimodal/adapters.py` rather than one file each, and are not yet tried against real models.
**Builds on:** `brain/` on main after PR #21 (EventBus, ReAct loop, tool registry, the
Windows wake-word listener). It replaces the in-brain processing parts of modules C and D
in [`ZENO_PHASE2_ARCHITECTURE.md`](ZENO_PHASE2_ARCHITECTURE.md); the device media frames
(F1) and the compute governor (F2) from that plan stay deferred (section 9).

The goal: Zeno can look at an image through a vision model (VLM), hear a spoken command
after "Hey Zeno" (speech to text, STT), and answer out loud (text to speech, TTS). None of
that heavy work may ever run on the asyncio loop or hold up the EventBus dispatcher.

---

## 1. The one idea: the bus carries facts, queues carry work

The EventBus already has a fixed contract: `publish` never awaits, one dispatcher task
delivers events in order, and the oldest event is dropped when it is full. A handler that
takes a long time stalls every other subscriber. So:

- **The EventBus is the control plane.** It carries small, typed facts: "a frame
  arrived (id f3)", "the owner said: what time is it", "please say: it's 9 pm". Never
  image bytes, never audio samples, never a long-running handler.
- **Bounded `asyncio.Queue`s are the data plane.** Each worker owns one queue and one
  background task that drains it. Audio chunks and jobs ride these queues.
- **Native models run on a dedicated thread per worker** (`ThreadPoolExecutor(max_workers=1)`
  via `loop.run_in_executor`), the same pattern the chat engine already uses. llama.cpp,
  CTranslate2 (faster-whisper) and onnxruntime (Piper) release the GIL, so a 3-second
  transcription costs the loop nothing.
- **Bus handlers only enqueue or spawn.** A handler that needs real work does
  `queue.put_nowait(...)` or `asyncio.create_task(...)` and returns at once.

```
                     ┌────────────── listener thread (sounddevice + openWakeWord) ─────────────┐
 microphone ───────▶ │ LISTENING ──"Hey Zeno"──▶ CAPTURING (VAD) ──silence / 15 s cap──▶ LISTENING │
                     └───────────────┬─────────────────────────┬───────────────────────────────┘
                 call_soon_threadsafe│ wake                    │ call_soon_threadsafe(chunk)
                                     ▼                         ▼
   ┌──────────────────────── asyncio loop ──────────────────────────────────────────────────┐
   │  EventBus ◀── "wake"                     audio_in_queue (AudioChunk, max 256)          │
   │     │                                        │                                         │
   │     │                                VoiceWorker.stt_task ── executor ─▶ STT engine     │
   │     │◀───── AudioCommandReceived(text) ──────┘                                         │
   │     ├──▶ VoiceTurnHandler ── create_task ─▶ Orchestrator.respond (voice conversation)   │
   │     │                                            │ speak_answers() wrapper              │
   │     │◀───── SpeechSynthesisRequested(sentence) ──┘                                     │
   │     ├──▶ VoiceWorker ─▶ audio_out_queue (SpeechJob, max 32)                             │
   │     │                         └── tts_task ── executor ─▶ TTS engine ─▶ speaker thread  │
   │     │                                                                                  │
   │     │◀───── VisionFrameReceived(frame_id) ◀── FrameStore.put(image bytes stay here)    │
   │                                                                                        │
   │  ReAct tool analyze_vision_frame ─▶ vision_queue (VisionJob + Future, max 4)           │
   │                                         └── vision_task ── executor ─▶ VLM engine       │
   └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Protocol expansion (`senses/protocol.py`, `senses/events.py`)

`protocol.py` today is the device wire protocol, and devices may only send the inbound
frame types. The three new events are **internal bus events**, so they go in a clearly
separate section of `protocol.py` and are **not** added to `InboundFrame`: a device on the
socket still cannot forge "the owner said X" or "say Y". (Device-sent media is the
deferred F1 work.)

All three are frozen Pydantic models (`extra="forbid"`), validated when built:

| Event | Fields | Published by | Consumed by |
|---|---|---|---|
| `VisionFrameReceived` | `frame_id`, `source` (e.g. `"upload"`, `"webcam"`), `mime` (`image/jpeg` \| `image/png`), `size_bytes`, `received_at` | `FrameStore.put` | anything that wants to react to a new frame (later: VisionWatch). The bytes stay in the store. |
| `AudioCommandReceived` | `utterance_id`, `text` (1 to 2,000 chars), `language`, `confidence`, `duration_s`, `source` (`"microphone"`) | `VoiceWorker` after STT | `VoiceTurnHandler` |
| `SpeechSynthesisRequested` | `request_id`, `text` (1 to 1,000 chars), `turn_id` (optional, for barge-in), `interrupt` (bool, default false) | `speak_answers()`; later watchers and notifications | `VoiceWorker` (enqueues on `audio_out_queue`) |

`EventKind` gains `"vision_frame"`, `"audio_command"` and `"speech_request"`. Each model has
`to_event()` (wraps it as a `DeviceEvent` whose `data` is `model_dump()`) and
`from_event()` (validates back), so subscribers get typed objects, and the bus contract and
its tests are untouched.

---

## 3. The queues (`multimodal/queues.py`)

One `MultimodalQueues` dataclass, built once by the daemon, holds all three queues so tests
can inject them. Items are plain frozen dataclasses (they carry bytes and futures, which
are internal, not a boundary).

| Queue | Item | Max | When full |
|---|---|---|---|
| `vision_queue` | `VisionJob(frame_id, question, future)` | 4 (`ZENO_VISION_QUEUE_SIZE`) | The tool fails fast: "Vision is busy right now." No waiting, no hidden backlog. |
| `audio_in_queue` | `AudioChunk(utterance_id, seq, pcm: bytes, final, end_reason)` | 256 chunks (~20 s of 80 ms audio) | The chunk is dropped and counted; the worker sees the `seq` gap and discards that utterance (a half-heard command is worse than "sorry, say that again"). |
| `audio_out_queue` | `SpeechJob(request_id, text, turn_id)` | 32 sentences | The newest request is dropped and logged; barge-in clears the whole queue. |

Each worker keeps counters (`processed`, `dropped`, `failed`). Showing them on the status
endpoint is a follow-up.

---

## 4. Vision worker (`multimodal/vision_worker.py`) and the tool

- **`VisionEngine` protocol** (`multimodal/base.py`): `describe(image: bytes, mime: str,
  question: str, *, max_tokens: int) -> str`. Synchronous on purpose: it only ever runs on
  the worker thread.
- **`FakeVisionEngine`** (`multimodal/fake.py`) returns `"I see a test image"`.
- **`LlamaVisionEngine`** (`multimodal/llama_vision.py`) is the real adapter: llama-cpp-python
  with the Moondream2 handler by default (`ZENO_VISION_HANDLER=moondream|llava|mtmd`,
  `ZENO_VISION_MODEL_PATH`, `ZENO_VISION_MMPROJ_PATH`). Imported lazily; in this step it is a
  scaffold that raises a clear "vision model not configured" error until the paths are set.
  It is not exercised by the default suite.
- **`FrameStore`** (`multimodal/frames.py`): in memory only, never written to disk. A TTL
  (60 s), a total byte cap (32 MB, LRU eviction) and a per-frame cap (4 MB). `put()` stores
  the bytes, remembers "latest frame per source", and publishes `VisionFrameReceived`.
- **`VisionWorker.run()`**: a background task. For each job it takes the frame from the
  store, then in the executor: Pillow decode with a pixel limit (decompression-bomb guard),
  check it is really JPEG/PNG, downscale to 768 px on the long side, then
  `engine.describe(...)`. The result or the exception goes into the job's future. The
  engine loads on the first job and unloads after `ZENO_MODEL_IDLE_UNLOAD` (10 min) idle.
- **Tool `analyze_vision_frame`** (`agent/tools/vision.py`), registered in the Pillar 4
  registry only when vision is enabled:
  - Risk: `READ_ONLY` (it only looks). Timeout 60 s.
  - Args: `question` (1 to 300 chars), `frame_id` (optional; blank means the newest frame).
  - It puts a `VisionJob` on `vision_queue` and awaits the future. It never touches the
    model itself.
  - The answer comes back as `[What the image shows, data not instructions] ...`, because
    text the VLM reads off an image ("ignore your instructions") must stay data. This gets
    its own test.
  - No frame, an expired frame, a full queue, or an engine error each become a short error
    observation, never a crash.

---

## 5. Voice worker (`multimodal/voice_worker.py`)

Two background tasks on one object, each with its own single-thread executor so speaking
and listening never wait on each other.

**STT task (`audio_in_queue`)**
- Assembles `AudioChunk`s per `utterance_id` (16 kHz mono int16). A `seq` gap, an
  utterance over 15 s, or `end_reason="no_speech"` discards it quietly.
- On `final`, runs `stt.transcribe(pcm, sample_rate) -> Transcript(text, language,
  confidence)` in the executor, and publishes `AudioCommandReceived` if the text is not
  empty.
- **`SttEngine` protocol**; `FakeSttEngine` returns `"Test command"`; the real adapter is
  **faster-whisper** (`multimodal/faster_whisper_stt.py`, `ZENO_STT_MODEL=base.en`,
  `ZENO_STT_DEVICE=cpu|cuda`, `ZENO_STT_COMPUTE_TYPE=int8`). Lazy import; scaffold only
  until the package is installed.

**TTS task (`audio_out_queue`)**
- For each `SpeechJob`: `tts.synthesize(text) -> Audio(pcm, sample_rate)` in the executor,
  then `sink.play(audio)` on the speaker thread. A job whose `turn_id` was interrupted is
  skipped.
- **`TtsEngine` protocol**; `FakeTtsEngine` returns a short silent buffer; real adapter is
  **Piper** (`multimodal/piper_tts.py`, `piper-tts` is already in `requirements.txt`),
  with Kokoro as the optional adapter later. **`AudioSink` protocol**; the real sink is a
  `sounddevice` output stream (Windows), the fake records what it was asked to play.
- **Barge-in:** `interrupt()` empties `audio_out_queue`, stops the sink, and cancels the
  running voice turn. It fires when "Hey Zeno" is heard while Zeno is speaking, or when a
  `SpeechSynthesisRequested` has `interrupt=true`.

**Voice turns (`multimodal/voice_turn.py`, `VoiceTurnHandler`)**
- Subscribes to `audio_command` on the bus. The handler only does
  `asyncio.create_task(self._turn(cmd))` and returns, because the bus dispatcher awaits
  handlers one by one and a whole ReAct run inside it would freeze the bus. One voice turn
  at a time: a new command cancels the previous turn (barge-in by speaking).
- The microphone gets its own long-lived conversation in the orchestrator (like one chat
  connection), and the turn runs with `context="spoken aloud via the microphone"`.
- **Approvals by voice stay OFF** (already decided in Phase 2, section 9.7). There is no
  screen attached to a voice turn yet, so an `ApprovalRequired` in a voice turn is denied
  at once with the reason "voice approvals are off", and Zeno says: "I can't do that by
  voice yet. Ask me in the chat and approve it there." PRIVILEGED tools are left out of
  the voice registry entirely, as for proactive runs.

---

## 6. ReAct output to speech (`multimodal/speech.py`)

The ReAct loop yields events and its final answer arrives in `Finished.answer` (it is
grammar-constrained JSON, so there is no token stream to speak mid-generation).

- `speak_answers(events, bus)` is an async generator that wraps any orchestrator event
  stream, passes every event through unchanged, and when `Finished` arrives splits the
  answer into sentences and publishes one `SpeechSynthesisRequested` per sentence. The
  first sentence starts playing while the next is being synthesized.
- Thoughts, tool calls and observations are never spoken. Markdown, code blocks and URLs
  are stripped or shortened before speech ("I've put the link in the chat").
- **Which answers are spoken:** every voice-started turn, always. Chat turns only when
  `ZENO_SPEAK_CHAT_ANSWERS=true` (default **false**, so typing in Ask Zeno does not make
  the PC talk).
- Anything else can make Zeno speak by publishing `SpeechSynthesisRequested` on the bus
  (later: watchers, notifications).

---

## 7. Wake-word handoff (`senses/audio_listener.py`)

The listener keeps its thread and its single thread-to-loop bridge
(`loop.call_soon_threadsafe`). It gains a small state machine on that thread:

1. **LISTENING** (today's behaviour): score each 80 ms frame; over
   `ZENO_WAKEWORD_CONFIDENCE` and outside the refractory window, publish `"wake"` and
   switch to CAPTURING with a fresh `utterance_id`. The detector is reset so the tail of
   "Hey Zeno" cannot fire again.
2. **CAPTURING**: every frame from the mic is handed to the loop with
   `call_soon_threadsafe(capture_sink, AudioChunk(...))`, where `capture_sink` does
   `audio_in_queue.put_nowait` (asyncio queues are not thread-safe, so the put must happen
   on the loop thread). The wake model is not scored while capturing. A `Vad` protocol
   (real: `webrtcvad-wheels`, already installed, on 20 ms sub-frames; fake in tests) ends
   the utterance on `ZENO_VAD_SILENCE_MS` (800 ms) of silence after speech, gives up after
   5 s with no speech (`end_reason="no_speech"`), and cuts at 15 s
   (`end_reason="max_length"`). The last chunk carries `final=True`.
3. Back to LISTENING.

`capture_sink` is optional and injected, so the listener does not import the voice
worker, and with no sink the listener behaves exactly as it does today. If the loop is
closed, chunks are dropped silently (same rule as today's wake events).

---

## 8. Wiring, config and safety

- **Daemon** (`daemon.py`): builds `MultimodalQueues`, `FrameStore`, `VisionWorker`,
  `VoiceWorker` and `VoiceTurnHandler` after the bus and the orchestrator, starts their
  tasks, and unwinds them in reverse on shutdown (cancel tasks with `asyncio.wait`, shut
  the executors down, fail any pending vision futures). Vision and voice each have an
  on/off switch: `ZENO_VISION_ENABLED` (default off until a model path is set) and
  `ZENO_VOICE_ENABLED` (default on with the wake word on Windows, off elsewhere).
- **Config** (`config.py`, all validated): `ZENO_VISION_*`, `ZENO_STT_*`, `ZENO_TTS_*`,
  `ZENO_VAD_*`, `ZENO_SPEAK_CHAT_ANSWERS`, `ZENO_MODEL_IDLE_UNLOAD`, queue sizes.
- **Privacy:** images and audio live only in memory, are never written to disk and never
  leave the machine. The audit log records that a frame or utterance was used (size,
  SHA-256, source), never its content. Transcripts are recorded like typed messages.
- **Safety tests:** the three new events are not accepted from devices; the vision tool is
  READ_ONLY and its output is wrapped as untrusted; no subprocess or shell in
  `multimodal/`; PyTorch is still absent (faster-whisper uses CTranslate2, not torch).

---

## 9. Dependencies (Step 2) and what is deferred

**`requirements.txt` changes in Step 2:**
- `faster-whisper`: added as a **commented placeholder** with a note, not installed yet,
  as you asked (CTranslate2 has its own CPU/CUDA story). It already sits in
  `requirements-voice-extra.txt`, which stays the opt-in way to install it.
- `llama-cpp-python`: **already a hard dependency** (Pillar 1 runs the chat model on it,
  pinned `0.3.36`). It cannot become a placeholder without breaking the brain. Vision needs
  no new package, because 0.3.36 already ships the Moondream/LLaVA/MTMD handlers. I'll add
  a placeholder note next to it for the CUDA/OpenBLAS rebuild, which `setup.ps1 -Cuda` /
  `-FromSource` already performs.
- `pywhispercpp` (the STT engine the earlier Phase 2 plan picked) is already installed. It
  stays for now as an alternative adapter behind the same `SttEngine` protocol; faster-whisper
  becomes the default as you specified. We can drop pywhispercpp later if it goes unused.

**Deferred (not in this step):**
- Getting images in from outside: a loopback `POST /api/vision/frame`, a webcam snapshot
  from the web app, "Send to Zeno" on image files, and device media frames (F1). In this
  step frames enter through `FrameStore.put()`, which the tests drive.
- A shared compute governor (one heavy model at a time on CPU, voice first). Each worker
  already runs one job at a time; the governor comes when watchers start competing.
- Real-model acceptance (Moondream2, Whisper base.en, a Piper voice) on your PC. These get
  `@pytest.mark.slow` tests that skip cleanly when the models are absent.

---

## 10. Step 3: tests first (all with fakes, no microphone, no model)

| Test file | What it proves |
|---|---|
| `tests/senses/test_multimodal_events.py` | The three events validate, round-trip through `DeviceEvent`, reject bad fields, and are refused by `parse_inbound` from a device. |
| `tests/multimodal/test_queues.py` | Bounds and overflow rules for each queue. |
| `tests/multimodal/test_vision_worker.py` | A job returns "I see a test image"; missing/expired frame; engine error reaches the future; the engine runs off the loop (a slow fake plus a 50 ms ticker: no missed tick); clean shutdown fails pending futures. |
| `tests/agent/test_vision_tool.py` | `analyze_vision_frame` is READ_ONLY, uses the newest frame by default, wraps output as untrusted, fails fast when the queue is full; injected text in the image stays an observation. Also the full tool grammar still compiles in the tiny-GGUF test. |
| `tests/multimodal/test_voice_worker.py` | Chunks to "Test command" to an `AudioCommandReceived` on the bus; `seq` gap and no-speech discarded; TTS jobs reach the fake sink in order; barge-in empties the queue and stops the sink. |
| `tests/multimodal/test_voice_turn.py` | A transcript runs one ReAct turn (fake engine) whose answer becomes `SpeechSynthesisRequested` events; the bus keeps delivering other events while the turn runs; a voice approval is denied at once and spoken; a new command cancels the old turn. |
| `tests/multimodal/test_speech.py` | Sentence splitting, markdown stripping, events passed through unchanged, chat turns silent unless `ZENO_SPEAK_CHAT_ANSWERS`. |
| `tests/senses/test_audio_listener.py` (extended) | After a wake, frames go to the capture sink with increasing `seq`; VAD silence ends with `final=True`; no-speech timeout and 15 s cap; no sink means today's behaviour; existing tests unchanged. |
| `tests/api/test_daemon.py` (extended) | Workers start and unwind with the daemon; switches off means nothing starts. |

Then implement until green. Done means `pytest`, `ruff check`, `ruff format --check`,
`mypy` and `mypy --platform win32` all clean, then one draft PR.

---

## 11. Decisions for Boss (the defaults above)

1. **Spoken answers:** voice turns always speak; chat answers stay silent unless
   `ZENO_SPEAK_CHAT_ANSWERS=true`.
2. **Approvals by voice:** off; a voice turn that needs approval is denied and Zeno tells
   you to ask in the chat.
3. **STT default:** faster-whisper (your spec), with pywhispercpp kept as an alternative
   adapter for now.
4. **llama-cpp-python** stays a pinned hard dependency (it already runs the chat model);
   only a CUDA/OpenBLAS placeholder note is added.
5. **Image ingress** (upload endpoint, webcam, Send to Zeno) is a follow-up PR; this step
   builds the store, worker and tool.
