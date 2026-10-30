# Zeno Phase 2: J.A.R.V.I.S.-level augmentation

**Status:** approved by Boss 2026-10-20 with the defaults in section 9. Step 2 (dependencies and setup) done. Module A (tools) built; the rest follow in the order of section 8.
**Builds on:** [`ZENO_ARCHITECTURE.md`](ZENO_ARCHITECTURE.md) and the merged pillars in `brain/`.

Phase 2 adds four capabilities: sight, voice, proactive watchers, and a larger set of tools. The aim is that Zeno can notice things and speak up on its own, not only answer when asked. The rules from Phase 1 still hold:

- Our own orchestration only; no LangChain or LlamaIndex.
- Grammar-constrained ReAct.
- Pydantic at every boundary.
- An approval from the owner before anything changes state.
- Loopback-only servers in v1.
- TDD one module at a time.

---

## 0. What exists today (the baseline this plan plugs into)

| Piece | Where | What matters for Phase 2 |
|---|---|---|
| Chat model | `inference/llama_cpp.py` | One dedicated worker thread per model; the event loop never blocks. Grammar validation before sampling (an invalid grammar segfaults). |
| Memory | `memory/` | ChromaDB plus our own embedder. Working memory per conversation. |
| Senses | `senses/server.py`, `protocol.py`, `manager.py`, `events.py` | Device socket using **JSON text frames only** (binary frames are refused today). Devices declare capabilities in `hello`. The `EventBus` never awaits in `publish`, drops the oldest event when full, and has one dispatcher task. Commands flow brain → device and are request/response with a timeout. |
| Agent | `agent/loop.py`, `policy.py`, `tools/` | Tools are `@tool(risk=READ_ONLY \| MUTATING)` with Pydantic args. MUTATING always waits for `ApprovalRequest`, and no answer means denied. Everything goes to the JSONL audit log. `test_safety.py` bans eval/exec/shell, and only `tools/scripts.py` may start a process. |
| Orchestrator | `orchestrator.py`, `daemon.py`, `api/` | `ZenoDaemon` boots in a fixed order inside the app lifespan and unwinds on failure. The chat socket streams thoughts, tool calls, approvals and answers. An approval resolves only on the connection that received it. |
| Web app | `src/ai/zenoBrain.ts` (PR #19) | One persistent socket per Next server, and Approve / Deny in Ask Zeno. |

**The two gaps everything below has to close:**

1. **Bytes.** Devices can't send images or audio yet, and the bus must never carry big payloads.
2. **Somebody to ask.** Today an approval needs a chat turn that is waiting on an open connection. A watcher that wakes up at 3 a.m. has neither.

---

## 1. Cross-cutting foundations

The four modules share four foundations. Each foundation is built inside the first module that needs it, with its own tests, and not as a separate "framework" step.

### F1. Media frames on the device socket (needed by vision and voice)

- **Protocol v1 stays compatible.** JSON frames are unchanged. New devices may also send **binary frames**, but only for a stream they opened with a JSON header first:
  - `media_start {stream: 0-255, kind: "image" | "audio", format: "jpeg" | "pcm16", rate?, channels?, bytes_max}` → binary frames → `media_end {stream}`.
  - Each binary frame is `[stream:u8][seq:u16 BE][payload]`. A gap in `seq` drops the stream; we don't try to repair it.
- **Capabilities gate it:**
  - `camera.jpeg`: the device can send images, and can be asked for one with a `camera.capture` command.
  - `mic.pcm16`: the device streams microphone audio.
  - `speaker.pcm16`: the brain may stream audio back to it.
  - A device that didn't declare the capability gets `undeclared_capability`, which counts as a strike under the existing strike rules.
- **Hard limits** live in config: max image bytes (default 256 KB), max open streams per device (2), max audio seconds buffered (30 s), and max frame bytes (unchanged). The socket loop only appends bytes to a bounded buffer and returns.
- **Bytes never ride the EventBus.**
  - Finished media goes into a `MediaStore`: in memory, a TTL (default 60 s), and LRU-capped total bytes.
  - The bus then gets a small event: `DeviceEvent(kind="media", data={"blob": id, "kind": ..., "bytes": n})`.
  - The bus contract (non-blocking `publish`, drop oldest) is untouched.
- **Camera frames use a "latest frame" slot** per device, not a queue. A camera pushing 5 fps can never build a backlog, because the analyser always takes the newest frame.
- **Audio uses a ring buffer** per device; the oldest samples drop when the consumer lags.
- **Privacy defaults:**
  - Images and audio are never written to disk unless `ZENO_MEDIA_ARCHIVE_DIR` is set.
  - They are never sent off this machine.
  - The audit log records that an image or utterance was used (size, hash, device), never the content.

### F2. Model workers and a compute governor (needed by vision and voice)

- **Every heavy model gets the pattern the chat engine already uses:** one dedicated worker thread owns the native model, and async callers get futures.
  - Generic base: `zeno/compute/worker.py` (`ModelWorker`).
  - It handles load, close, cancel and a bounded job queue.
- **`ComputeGovernor`** (`zeno/compute/governor.py`) is an async priority semaphore for "heavy slots".
  - Default: 1 slot on CPU (`ZENO_COMPUTE_SLOTS`), because running three models at once on a CPU makes all of them slower.
  - Priorities, highest first:
    1. Voice: speech-to-text and text-to-speech, because a person is waiting mid-sentence.
    2. Interactive chat.
    3. Vision someone asked for.
    4. Background and watcher work.
  - Background jobs never take a slot while a higher-priority job is waiting.
  - Jobs carry deadlines, and a job past its deadline is dropped instead of run late.
- **Lazy load with idle unload:**
  - The VLM and the speech-to-text (STT) model load on first use and unload after `ZENO_MODEL_IDLE_UNLOAD` (default 10 min).
  - The chat model stays resident, as today.
  - This keeps RAM sane on a laptop: a small chat model plus Moondream plus Whisper base is roughly 4 GB with everything loaded.
- **Why threads and not processes:** llama.cpp, whisper.cpp and onnxruntime release the GIL. Each worker hides behind a protocol, so a process-backed adapter can be swapped in later for crash isolation without touching callers. If we ever do that, the safety test gets an explicit allowlist entry for `zeno/compute/`.

### F3. The owner hub: notifications and approvals without an open turn (needed by watchers, used by all)

- **`OwnerHub`** (`zeno/owner.py`) is the brain's single way to reach Boss.
  - Every authenticated chat connection registers with it.
  - Later, a device with `speaker.pcm16` can register as an "announce only" outlet.
- **New outbound chat frames:**
  - `notification {id, severity: info | warning | critical, title, body, source, at}`
  - `approval_required` gains `origin: "chat" | "proactive"`.
- **Approval routing:**
  - **Chat turns** keep today's rule: only the connection that asked can answer.
  - **Proactive runs** broadcast the request to every owner connection. The first answer wins, and the others receive the `approval` frame so their cards close.
  - **Nobody connected** means a proactive mutating action is **denied straight away**. The notification queues (bounded, newest kept) and is delivered on the next connect.
- **Web app:** `ZenoLink` already holds a persistent socket. It forwards `notification` frames to the browser over a new `GET /api/ai/events` (Server-Sent Events). Ask Zeno shows a toast, and the existing approval card is reused.

### F4. A third risk tier: `PRIVILEGED` (needed by SSH, reused by MQTT if wanted)

- **`Risk.PRIVILEGED`:**
  - Always needs approval, like MUTATING.
  - Is **never offered to proactive runs**: the registry a watcher gets doesn't contain these tools at all, so the grammar can't even name them.
  - The approval card shows the exact command, and the audit record stores it in full.
- `needs_approval` is unchanged for existing tools. The policy gains `available_in(origin)`.

---

## 2. Module A: Advanced tools (web, network, SSH, MQTT)

**Recommended first.** It needs no new model, delivers value immediately, and introduces F4. MQTT also becomes a second source of senses for module B.

| Tool | Risk | Design |
|---|---|---|
| `web_search(query, max_results)` | READ_ONLY | Queries a **self-hosted SearXNG** JSON API (`ZENO_SEARCH_URL`, default unset, which means the tool isn't registered). Results are title, URL and snippet, capped. |
| `fetch_page(url)` | READ_ONLY | `httpx` with http(s) only. **SSRF guard:** the URL is resolved first and must point to a public address, and this is re-checked on every redirect (max 5); there's a toggle for LAN addresses. Caps: 2 MB and 10 s. HTML becomes text with `selectolax`. The observation is wrapped as untrusted web content. |
| `ping(host, count)` | READ_ONLY | `icmplib` in unprivileged mode, so no subprocess (the safety test stays as is). |
| `dns_lookup(name, type)` | READ_ONLY | Async resolver (`asyncio` getaddrinfo, plus A/AAAA/MX via `dnspython` if needed). |
| `port_check(host, port)` | READ_ONLY | One TCP connect with a timeout. **No range scans.** |
| `network_status()` | READ_ONLY | `psutil`: interfaces, addresses, link state, throughput counters. |
| `ssh_run(host, command)` | **PRIVILEGED** | `asyncssh` details below. |
| `mqtt_read(topic)` | READ_ONLY | Latest retained or seen value from the MQTT cache, only for topics in the allowlist. |
| `actuate_<name>(...)` | MUTATING | One tool per actuator the owner declares (details below). |

**SSH details:**
- Hosts come from an owner-curated `data/ssh_hosts.json`, with alias, host, user and key path.
- **Strict known_hosts**: an unknown key is refused, never trust-on-first-use.
- Key authentication only; no passwords are stored.
- The command is validated: a single line, at most 1,000 characters, no NUL.
- Output is capped and there is a timeout.

**MQTT actuation:**
- Actuators come from `data/mqtt.json` (with the broker and the readable topics), each with a topic, a payload schema, QoS and a description.
- The schema is a **restricted subset**: enum, bounded number, bool and short string. It's compiled into a Pydantic model, so the grammar constrains the values and `light.set(brightness=900)` can't even be generated.
- Publishing uses `aiomqtt`.

**MQTT as a sense:**
- An `MqttSense` subscribes to allowlisted topics and publishes `DeviceEvent(device="mqtt:<broker>", kind="sensor")` onto the existing bus.
- Watchers and `read_sensor` then treat Zigbee2MQTT or Home Assistant data like any device.

**Safety updates in `test_safety.py`:**
- Outbound network imports (`httpx`, `asyncssh`, `aiomqtt`, `icmplib`) are allowed only in their own tool modules.
- Still no subprocesses, and still no shell.
- A new test fails if any PRIVILEGED tool appears in the proactive registry.

**Egress is opt-in:** each network tool registers only when its config exists (search URL, SSH hosts file, MQTT broker). A fresh install behaves exactly like today.

---

## 3. Module B: Proactive watcher daemons

- **`WatcherManager`** (`zeno/watchers/`) is started by `ZenoDaemon` after the tools, and unwound before them.
  - Each watcher is a small async task that reads state, never acts, and emits `Finding`s.
  - It runs on a jittered interval and sits under the governor's lowest priority, so it can never starve chat or voice.
- **Built-in watchers:**
  - `SystemHealth` (`psutil`): CPU, RAM, disk free, temperature where available, plus the brain's own health (event-bus drops, model worker queue depth, audit write failures).
  - `NetworkWatch`: gateway reachable, internet reachable (TCP to a configurable target), DNS working, and an interface changed.
  - `SensorThreshold`: subscribes to the EventBus. Owner rules live in `data/watchers.json`, for example `{device, sensor, op: ">" | "<" | "outside", value, for_seconds, clear_at}`.
    - Rules are **data, not code**: Pydantic validates them, there's no expression language, and nothing is evaluated.
    - **Hysteresis** (`clear_at`) and a **sustain time** (`for_seconds`) stop a sensor sitting on the threshold from flapping.
  - `VisionWatch` (added by module C): periodically asks the VLM a fixed question about a camera, such as "is there a person at the door?". It's rate-limited (default every 60 s) and runs at the lowest priority.
- **From finding to action:**
  1. Every `Finding` gets a stable key (watcher, subject) and is **de-duplicated**.
  2. **Cooldowns** apply per key (default 15 min), and a **global budget** applies (default 6 proactive runs per hour).
  3. `info` findings only notify.
  4. `warning` and `critical` findings start a **proactive ReAct run** through the orchestrator, in a dedicated "watch" conversation. The prompt says what was observed, and observed values are treated as untrusted data.
  5. The tools in that run are read-only ones plus `notify_owner(severity, title, body)`. Mutating tools go to the owner hub and are denied if nobody is there. PRIVILEGED tools aren't present at all.
  6. The run's answer becomes a notification. If a speaker device is registered, it's spoken (module D).
- **Kill switch:** `ZENO_WATCHERS_ENABLED`, plus `pause_watchers` (and resume) from the chat socket.
- Every finding, suppression and proactive run is audited, with the trigger that caused it.

---

## 4. Module C: Visual cortex (sight)

- **`VisionEngine` protocol** (`zeno/vision/base.py`): `describe(image: ImageInput, question: str, *, max_tokens) -> str`.
  - Implementation: `LlamaVisionEngine` on llama-cpp-python 0.3.36, which already ships `MoondreamChatHandler`, `Qwen25VLChatHandler` and the generic `MTMDChatHandler` (libmtmd). **No new inference dependency.**
  - The model is a `.gguf` plus its `mmproj` file (`ZENO_VISION_MODEL_PATH`, `ZENO_VISION_MMPROJ_PATH`, `ZENO_VISION_HANDLER`).
  - It runs on its own `ModelWorker` thread under the governor.
- **Image intake:**
  - `Pillow` decodes with a pixel limit (guards against decompression bombs) and verifies the image is really JPEG or PNG.
  - It's downscaled to the model's input size (for example 768 px on the long side) and re-encoded.
  - The result is passed to the handler as a data URI. Nothing touches disk.
- **Getting a picture:**
  - **Pull:** the `look(device, question)` tool (READ_ONLY) sends `camera.capture` to the device. It waits for the matching `media_end` (correlated by the command id), takes the blob from the `MediaStore`, and asks the VLM. The answer comes back as an untrusted observation.
  - **Push:** an ESP32-CAM streaming frames keeps updating its latest-frame slot, and `look` uses the newest frame if it's younger than `ZENO_VISION_MAX_AGE` (default 2 s) instead of asking for a fresh one.
  - **Web app:** later, Ask Zeno could also send a webcam snapshot through the same `look` path. That's out of scope unless you want it.
- **Prompt injection:** text the VLM reads in an image (a sign saying "ignore your instructions") comes back as observation data, which the agent already treats as untrusted. This gets a dedicated test.

---

## 5. Module D: Vocal tract (voice)

```
device mic ─ media(pcm16 16 kHz) ─▶ AudioSession ring buffer ─▶ utterance end ─▶ STT worker ─▶ transcript
   ▲                                                                                   │
   └─ media(pcm16) ◀─ TTS worker (sentence by sentence) ◀─ answer text ◀─ orchestrator turn (device's own conversation)
```

- **Utterance boundaries:**
  - The device decides with push-to-talk or its own wake word, and sends `listen_start` and `listen_end`. That's the reliable path for ESP32s.
  - The brain-side VAD (`webrtcvad-wheels`) is the fallback for always-on mics. It ends an utterance after `ZENO_VAD_SILENCE_MS`.
  - A cap on utterance length applies (default 15 s).
- **STT:**
  - `SttEngine` protocol; the default is **whisper.cpp via `pywhispercpp`**, which comes from the same ggml family as llama.cpp and has the same CPU-to-CUDA swap story.
  - `faster-whisper` is the alternative adapter if pywhispercpp wheels misbehave on Windows.
  - The model is `ggml-base.en.bin` by default (`ZENO_STT_MODEL_PATH`).
- **The turn:**
  - Each voice device gets its **own conversation** in the orchestrator, the same way each chat connection does.
  - The transcript runs a normal turn with `context` set to "spoken via <device>".
  - The answer streams to TTS as soon as the first sentence is complete, so speech starts before generation finishes.
- **TTS:**
  - `TtsEngine` protocol; the default is **Piper** (`piper-tts`, onnxruntime). It's fast on CPU, has many voices, and gives low first-audio latency.
  - Kokoro (`kokoro-onnx`) is an optional adapter, which matches the web app's Kokoro voice.
  - Output is resampled to the device's declared rate and streamed as `media` frames to `speaker.pcm16`, with paced sending so a slow ESP32 isn't flooded.
- **Barge-in:** when the device sends `interrupt` (or a new `listen_start` arrives), the brain stops sending TTS audio, cancels the turn, and drops the queued audio.
- **Approvals by voice are OFF by default.** A spoken "yes" can come from a TV or anyone in the room.
  - Voice-started turns that need approval show the card in the web app and say "check your screen to approve".
  - Allowing a spoken yes for MUTATING (never PRIVILEGED) is a later opt-in, if you want it.
- **The web app keeps its own browser voice for now.** Routing browser audio to the brain's STT and TTS is possible later over the same media frames.

---

## 6. Non-blocking guarantees (how each constraint is enforced and tested)

| Guarantee | Mechanism | Test |
|---|---|---|
| Socket loops never wait on a model | Socket code only appends to bounded buffers and publishes small events | A fake VLM that blocks forever; heartbeats and pings on the same device and on other devices are still answered on time |
| The bus never carries bytes | `MediaStore` blob ids only | The bus test asserts each event's payload size |
| Native models never run on the event loop | `ModelWorker` thread per model; the governor hands out slots | Loop-lag probe: a fake slow model plus a 50 ms ticker; a missed tick fails the test |
| Background work can't starve people | Governor priorities, deadlines and drop-on-expiry | A watcher floods the queue; a chat turn still gets the next slot |
| A watcher can't spam or loop | De-duplication, cooldown and a global budget | A flapping sensor fake produces exactly one run per cooldown |
| A proactive run can't act alone | Owner hub; denied without an owner; PRIVILEGED absent | Tests for: no owner gives a denial, and the grammar can't name `ssh_run` |
| Media can't exhaust memory | Byte caps, stream caps, TTL and LRU | Oversized and endless streams are cut off and the device gets a strike |

All new default tests use fakes (`FakeVision`, `FakeStt`, `FakeTts`, an in-memory MQTT broker, `httpx.MockTransport`, a local `asyncssh` test server on 127.0.0.1, and a controllable clock). The new tests together should run in under 10 s. Real-model tests are `@pytest.mark.slow`, like today. New tool schemas join the tiny-GGUF test that compiles the **full** tool grammar in llama.cpp; that test caught a real bug in Phase 1.

---

## 7. Step 2 preview: dependencies and setup

**Runtime (`requirements.txt`, pinned at Step 2):**

| Package | Used by | Version checked |
|---|---|---|
| `pillow` | Vision intake | 13.0.0 |
| `numpy` | Audio buffers and resampling | 2.5.4 |
| `pywhispercpp` | STT (whisper.cpp) | 1.5.1 |
| `piper-tts` (brings `onnxruntime`) | TTS | 1.8.0 |
| `webrtcvad-wheels` | VAD | 2.0.14.post1 |
| `psutil` | Watchers, `network_status` | 7.2.2 |
| `icmplib` | `ping` with no subprocess | 3.0.4 |
| `httpx` (moves from dev to runtime) | `web_search`, `fetch_page` | 0.28.1 |
| `selectolax` | HTML to text | 1.0.1 |
| `asyncssh` | `ssh_run` | 2.24.1 |
| `aiomqtt` | MQTT sense and actuation | 2.5.1 |

- **Vision:** no new package. llama-cpp-python 0.3.36 already includes the multimodal handlers. Only model files are needed.
- **Optional extras** (`requirements-voice-extra.txt`): `kokoro-onnx`, `faster-whisper`.
- **Setup scripts** gain:
  - `-Voice` / `--voice` and `-Vision` / `--vision`, which print the model files to download and where to put them (`brain/models/`, which stays git-ignored). Models are never downloaded silently.
  - The CUDA path gets matching notes for whisper.cpp and `onnxruntime-gpu`.
- **New `ZENO_*` settings**, all in `config.py` with validation:
  - Vision: `ZENO_VISION_*`.
  - Speech: `ZENO_STT_*`, `ZENO_TTS_*`, `ZENO_VAD_*`.
  - Media: `ZENO_MEDIA_*`.
  - Compute: `ZENO_COMPUTE_SLOTS`, `ZENO_MODEL_IDLE_UNLOAD`.
  - Watchers: `ZENO_WATCHERS_*`.
  - Tools: `ZENO_SEARCH_URL`, `ZENO_MQTT_*`, plus the SSH, actuator and watcher file paths.

---

## 8. Build order and TDD steps

Each module merges as its own draft PR, after `pytest`, `ruff check`, `ruff format --check` and `mypy --strict` pass, and your approval.

| # | Module | Tests first (examples) | Then build |
|---|---|---|---|
| A | Tools (+F4) | SSRF (private IP, redirect into LAN, DNS rebinding); size and time caps; untrusted wrapping; PRIVILEGED never in the proactive registry; unknown SSH host key refused; actuator schema bounds in the grammar; MQTT allowlist; full-grammar llama.cpp compile | Risk tier, web, network, SSH, MQTT tools, MqttSense |
| B | Watchers (+F3) | Hysteresis and sustain; de-duplication, cooldown and budget; proactive run with no owner gives a denial and a queued notice; broadcast approval, first answer wins; `notification` frames; SSE route in the web app | OwnerHub, WatcherManager, built-in watchers, notify tool, web toast |
| C | Vision (+F1, F2) | Media frame parsing (seq gap, oversize, undeclared); latest-frame slot; governor priority and deadlines; loop-lag probe; `look` pull and push paths; decompression bomb; injected text stays an observation | Media protocol, MediaStore, ModelWorker, Governor, LlamaVisionEngine, `look`, VisionWatch |
| D | Voice | Ring buffer overflow; listen_start/end and VAD boundaries; per-device conversation; sentence-by-sentence TTS start; paced output; barge-in cancels turn and audio; voice approvals off | AudioSession, Whisper adapter, Piper adapter, voice turn loop, device simulator update |

**Why this order:** each module stands on the previous one.
- **A** adds no models and introduces the strict tier.
- **B** needs the owner hub, which every later module uses to speak up.
- **C** builds the media and compute plumbing with the simpler direction (bytes in, text out).
- **D** reuses all of it and adds the hard part (real-time audio both ways).

---

## 9. Decisions for Boss (defaults this plan assumes)

1. **Build order:** A tools → B watchers → C vision → D voice. *(Your list was vision first; the reasons are in §8.)*
2. **Speech-to-text:** whisper.cpp via `pywhispercpp`, with `faster-whisper` as the fallback adapter.
3. **Text-to-speech:** Piper by default, with Kokoro as an optional adapter that matches the web app's voice.
4. **Vision model:** Moondream2 by default (small, CPU-friendly); Qwen2.5-VL 3B as the quality option via the MTMD handler.
5. **SSH:** any single-line command on allowlisted hosts. It needs your approval every time, it's never available to watchers, and unknown host keys are refused. *(The stricter alternative is per-host command allowlists only.)*
6. **Web search:** a self-hosted SearXNG, off until you set its URL. *(The alternative is scraping DuckDuckGo's HTML page directly, which is less private and more brittle.)*
7. **Voice approvals:** off; approvals happen on screen.
8. **Outbound network:** each network tool is opt-in through its own config.
9. **Edge devices on the LAN (needs your call):** the brain listens only on 127.0.0.1 in v1, so a real ESP32-CAM or Pi **can't reach it yet**. Modules A and B don't depend on this.
   - Modules C and D can be fully built and tested with the device simulator on this PC.
   - Using real hardware needs the planned v1.1 step first: binding to the LAN with TLS (`wss://`, a self-signed certificate the devices pin, and the per-device tokens that already exist).
   - **Default:** do that v1.1 step as a small separate PR between B and C.

**Pre-existing open item:** PR #19 (wiring Ask Zeno to the brain) is still a draft. Module B's toast and approval routing build on it, so it should merge before module B starts.
