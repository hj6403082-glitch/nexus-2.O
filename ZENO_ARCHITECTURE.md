# Zeno Brain — Architecture & Implementation Plan

Status: **Approved 2026-10-19.** Step 2 (setup) done; see `brain/CLAUDE.md`. Decisions are in section 6.

## 0. Context and goals

The current Zeno is a Next.js/TypeScript web app (`src/`). Its "brain" is `src/ai/ollama.ts`, which streams chat from a local Ollama server, and `src/app/api/ai/route.ts`, which turns that into newline-delimited JSON events (`text`, `command`, `error`, `done`, defined in `src/ai/protocol.ts`).

This plan adds a **new, independent Python backend** (`brain/`) that owns the whole pipeline: model execution, memory, device I/O and tool use. It replaces Ollama as a dependency without breaking the web app: the web app gains one more provider (`AI_PROVIDER=zeno`) that streams the same `StreamEvent` protocol it already understands. Ollama, Grok and Gemini keep working until the brain is proven.

Design principles:

- **Own the pipeline.** No LangChain, LlamaIndex or Ollama. Every orchestration step (prompt assembly, retrieval, tool parsing, the ReAct loop) is plain Python we can read and test.
- **Ports and adapters.** Each pillar exposes a small `Protocol` interface; the concrete backend (llama.cpp, ChromaDB, …) sits behind it. Tests run against fakes, so the suite is fast and needs no GPU or model download.
- **Local-first and safe by default.** Everything binds to loopback unless explicitly configured; anything that touches the operating system goes through an allowlist and a policy layer.
- **Async throughout.** One `asyncio` event loop; blocking work (inference, embeddings) runs in worker threads so streaming and WebSockets stay responsive.

## 1. Pillar analysis and decisions

### Pillar 1 — Native inference engine

| Option | Pros | Cons |
|---|---|---|
| **llama-cpp-python** (GGUF) | Runs quantized 1–14B models on CPU or consumer GPU (CUDA/Vulkan/Metal); low RAM; streaming; built-in chat templates and grammar-constrained output (GBNF / JSON schema); same GGUF files Ollama uses | Wheels need a build toolchain for GPU variants; Python binding lags upstream slightly |
| **PyTorch + transformers** | Maximum flexibility, fine-tuning, research models | Multi-GB install, fp16 models need far more VRAM, slower on CPU, quantization is fiddlier |

**Recommendation: llama-cpp-python** as the default engine. It matches the hardware Zeno runs on (a Windows PC, possibly a Raspberry Pi edge), and its **grammar-constrained decoding** lets us force the ReAct loop's tool calls to be valid JSON, which removes the most common local-model failure. PyTorch stays possible later as a second `InferenceEngine` adapter (for fine-tuning experiments), not a v1 dependency.

Design:
- `InferenceEngine` protocol: `stream(messages, *, max_tokens, stop, grammar=None) -> AsyncIterator[Token]` and `count_tokens(text)`.
- `LlamaCppEngine` loads one GGUF model once at startup (path from config), keeps it resident, runs generation in a dedicated thread and bridges tokens to asyncio through a queue. A single-flight lock serialises generation (one model context), with a bounded request queue and cancellation when the client disconnects.
- `PromptBuilder` owns the chat template, a byte-stable system prompt (so the KV cache prefix is reused between turns, as the current Ollama code does) and a token budget that trims history and retrieved memories to fit `n_ctx`.
- A `ThinkFilter` port of the existing TypeScript one strips `<think>` blocks from reasoning models.
- Model files are managed by a small `models` CLI (list, verify checksum, download from a configured URL) so nobody needs a terminal beyond the launcher.

### Pillar 2 — Persistent memory

| Option | Pros | Cons |
|---|---|---|
| **ChromaDB (embedded `PersistentClient`)** | Stores vectors **and** documents + metadata; metadata filtering; persistence built in; no server process | Heavier dependency; less control over the index |
| **FAISS** | Very fast, tiny, full control | Vectors only: we'd have to build our own document store, metadata, deletion and persistence |

**Recommendation: ChromaDB in embedded mode**, behind a `VectorStore` protocol so FAISS (+ SQLite for documents) can be swapped in if we outgrow it. Zeno's memory volume (conversations, facts, notes) is small enough that Chroma's convenience wins.

Embeddings: computed **by us**, not by Chroma's default function, so the pipeline is explicit:
- Default: a small GGUF embedding model (e.g. `nomic-embed-text` or `bge-small`) through llama-cpp-python with `embedding=True`, so there's no PyTorch dependency.
- `Embedder` protocol makes this swappable.

Memory model (three tiers):
1. **Working memory** — the current conversation, held in RAM, trimmed by token budget.
2. **Episodic memory** — every finished exchange is summarised (by the model, asynchronously after the reply) and stored with timestamp, session and importance score.
3. **Semantic memory** — durable facts about the owner ("prefers green UI", "lives in …"), extracted with a constrained-JSON prompt, de-duplicated by similarity before insert, and editable/deletable by the owner.

Retrieval per turn: embed the user message → top-k from semantic + episodic → re-rank by `similarity × recency decay × importance` → inject within the token budget as clearly delimited *data, not instructions*. The existing `zeno-profile.json` owner profile is imported as seed semantic memory. Owner-facing endpoints: list, search, delete one, wipe all.

### Pillar 3 — Senses & hardware control (WebSocket server)

Framework: **FastAPI + Uvicorn** (native WebSocket support, Pydantic validation, also serves the HTTP chat endpoint the web app uses). One process, one event loop.

Protocol: a versioned JSON envelope, validated with Pydantic on both ends:

```json
{ "v": 1, "id": "uuid", "type": "hello|event|command|ack|result|ping|pong|error", "device": "pi-livingroom", "payload": {} }
```

- **Handshake & auth:** each device is registered with its own pre-shared token (stored hashed). First frame must be `hello` with device id + token + declared capabilities (e.g. `sensor.temperature`, `actuator.relay`, `camera.snapshot`). Unknown devices or bad tokens are closed immediately.
- **Transport security:** loopback by default; when edge devices on the LAN are enabled, bind to the LAN interface **with TLS** (`wss://`, self-signed CA generated at setup) and an explicit allowlist of device ids.
- **Device registry:** tracks connected devices, capabilities, last-seen; heartbeats (`ping`/`pong`) with timeouts; automatic cleanup on disconnect.
- **Sensor events** flow device → brain → an internal `EventBus` (asyncio pub/sub). Memory can store notable events; the agent can query the latest readings.
- **Commands** flow brain → device only for capabilities the device declared, with request ids, acks, timeouts and results. Payloads are size-limited and rate-limited per device.
- A reference **edge client** (`edge/zeno_edge.py`, pure Python + `websockets`) for Raspberry Pi with auto-reconnect and exponential backoff, plus a simulator used by tests.

### Pillar 4 — Agentic tool use (custom ReAct loop)

The loop (native, ~200 lines):

```
build prompt (persona + tool specs + memories + history)
loop up to MAX_STEPS:
    model output is grammar-constrained to either
        {"thought": "...", "action": {"tool": name, "args": {...}}}   or
        {"thought": "...", "final": "answer text"}
    if final: stream answer, store memory, stop
    validate args against the tool's Pydantic schema
    policy check → (allow | ask owner | deny)
    run tool with timeout, capture bounded output
    append observation (marked as untrusted data) and continue
```

Tools are Python classes registered in a `ToolRegistry`, each declaring a name, description, Pydantic args schema, a **risk level** and a timeout. Tool specs are rendered into the prompt and into the grammar automatically.

Safety model (this pillar touches the owner's machine, so it is deliberately conservative):
- **No free-form shell.** The model never supplies a raw command line. "System commands" are individual, named tools (e.g. `system_info`, `open_app`, `set_volume`, `list_directory` in allowed folders), each mapping to a fixed implementation with validated arguments, run via `subprocess` with an argument list (never `shell=True`).
- **Script runner** executes only scripts from a dedicated, owner-curated `brain/scripts/` folder, by name, with validated arguments, in a subprocess with timeout, working-directory confinement and output caps. It cannot run arbitrary code the model writes.
- **Policy layer:** read-only tools run automatically; tools that change state require owner confirmation (sent to the web app / voice as a yes/no prompt); anything not on the allowlist is denied. Every tool call is written to an append-only audit log.
- **Prompt-injection hygiene:** tool outputs, memories and device data are wrapped as untrusted observations and can never add tools or change policy.
- Limits: max steps, max wall time, max output size per observation; loop aborts cleanly on client cancel.

## 2. How the web app connects

- New provider `AI_PROVIDER=zeno` in the web app: `src/ai/zenoBrain.ts` keeps one chat socket to `ws://127.0.0.1:<port>/v1/chat/ws` per server process and turns its frames into the **existing** NDJSON `StreamEvent` shape (plus `approval` / `decided` events), so `EventDecoder`, the UI and the voice pipeline are unchanged. The brain keeps the conversation; the web app sends the newest message and what is on screen. Approvals come back through `POST /api/ai/approval` on the same socket.
- `/v1/status` reports `starting | ready | failed`; `zenoStatus()` maps it (and an unreachable brain to `offline`) onto the shape the existing status UI reads.
- UI commands (`transform`, `open`, …) become ReAct tools whose results are emitted as `command` events, validated by the existing `validateCommand`.
- The launcher (`scripts/windows/nexus.ps1`) later starts the Python brain instead of the Ollama app.

## 3. Proposed directory structure

```
brain/                          # new Python package, independent of the Next.js app
├── pyproject.toml              # project metadata, ruff/mypy/pytest config
├── requirements.txt            # pinned runtime deps
├── requirements-dev.txt        # pytest, pytest-asyncio, ruff, mypy, httpx
├── README.md
├── .env.example                # ZENO_MODEL_PATH, ZENO_PORT, ZENO_DATA_DIR, …
├── zeno/
│   ├── __init__.py
│   ├── __main__.py             # `python -m zeno` → starts server
│   ├── config.py               # pydantic-settings, single source of config
│   ├── logging.py              # structured logging + audit log
│   ├── protocol.py             # StreamEvent / WS envelope Pydantic models
│   ├── inference/
│   │   ├── base.py             # InferenceEngine, Token protocols
│   │   ├── llama_cpp.py        # LlamaCppEngine adapter
│   │   ├── prompt.py           # PromptBuilder, chat template, token budget
│   │   ├── grammar.py          # GBNF / JSON-schema builders
│   │   ├── think_filter.py
│   │   └── fake.py             # scripted engine for tests
│   ├── memory/
│   │   ├── base.py             # VectorStore, Embedder protocols
│   │   ├── chroma_store.py
│   │   ├── embedder.py         # llama.cpp embedding adapter
│   │   ├── manager.py          # tiers, retrieval, re-ranking, extraction
│   │   └── fake.py
│   ├── senses/
│   │   ├── server.py           # FastAPI WebSocket endpoint
│   │   ├── registry.py         # devices, capabilities, heartbeats
│   │   ├── auth.py             # device tokens (hashed), TLS helpers
│   │   └── events.py           # asyncio EventBus
│   ├── agent/
│   │   ├── loop.py             # ReAct loop, limits, loop detection
│   │   ├── steps.py            # step schema + grammar built from the registry
│   │   ├── policy.py           # approval requests for MUTATING tools
│   │   ├── audit.py            # append-only JSONL audit log
│   │   ├── events.py           # what a run yields (thought, call, approval, ...)
│   │   ├── registry.py         # ToolRegistry
│   │   └── tools/
│   │       ├── base.py         # @tool, ToolArgs, Risk (READ_ONLY / MUTATING)
│   │       ├── clock.py        # get_time
│   │       ├── calculator.py   # safe arithmetic (AST walk, no eval)
│   │       ├── system.py       # named system tools (fixed implementations)
│   │       ├── scripts.py      # curated script runner (brain/scripts/*.py)
│   │       ├── memory.py       # recall / remember
│   │       ├── devices.py      # list devices, read sensors, send commands
│   │       └── ui.py           # emits web-app commands
│   ├── api/
│   │   ├── app.py              # FastAPI app: status, chat socket, device socket
│   │   ├── chat.py             # /v1/chat/ws session: turns, approvals, cancel
│   │   ├── protocol.py         # chat frames (inbound validated)
│   │   └── auth.py             # chat bearer token (data/api-token)
│   ├── orchestrator.py         # wires pillars: message → memory → agent → stream
│   ├── daemon.py               # ZenoDaemon: ordered boot, serve, clean shutdown
│   └── __main__.py             # python -m zeno [serve | token]
├── scripts/                    # owner-curated scripts the agent may run
├── edge/
│   ├── zeno_edge.py            # Raspberry Pi reference client
│   └── simulator.py
└── tests/
    ├── conftest.py             # fakes, temp data dirs
    ├── inference/  memory/  senses/  agent/  api/
    └── integration/            # opt-in, needs a real GGUF (marked `slow`)
```

`brain/` lives alongside the existing app; nothing under `src/` changes until the integration step.

## 4. Step-by-step implementation plan

Each pillar follows TDD: write failing tests → implement → `pytest` green → only then move on. Real-model tests are marked `@pytest.mark.slow` and skipped by default; the default suite uses fakes and runs in seconds.

**Step 2 — Setup & verification (after approval)**
1. `CLAUDE.md` for the brain: how to run tests, code style (ruff, mypy strict, type hints, small modules, no LangChain/LlamaIndex), repo rules.
2. `brain/` skeleton, `pyproject.toml`, `requirements*.txt` with pinned versions, venv instructions for Windows and Linux/Pi.
3. `config.py` + `protocol.py` with their tests; CI-ready `pytest` + `ruff` + `mypy` commands.

**Step 3a — Pillar 1: inference**
1. Tests: PromptBuilder template output, byte-stable system prompt, token-budget trimming, ThinkFilter on split chunks, engine streaming/cancellation via the fake.
2. Implement `PromptBuilder`, `ThinkFilter`, `FakeEngine`, `LlamaCppEngine` (thread → asyncio bridge, single-flight lock).
3. Slow test: load a tiny GGUF and stream a reply.

**Step 3b — Pillar 2: memory**
1. Tests: store/retrieve round trip on a temp Chroma dir, persistence across restart, re-ranking order, de-duplication, delete/wipe, token-budgeted injection.
2. Implement `Embedder`, `ChromaStore`, `MemoryManager`, profile import.

**Step 3c — Pillar 3: senses**
1. Tests (FastAPI `TestClient` WebSockets): handshake accept/reject, capability gating, heartbeat timeout, command → ack → result, oversized/malformed frame handling, rate limiting.
2. Implement registry, auth, EventBus, server; edge client + simulator.

**Step 3d — Pillar 4: agent**
1. Tests with the scripted fake engine: final answer path, single and multi-step tool use, invalid tool / invalid args recovery, max-steps stop, policy (auto / confirm / deny), timeouts, audit log entries, untrusted-observation wrapping.
2. Implement Tool base, registry, parser, policy, loop, then the initial tool set.

**Step 3e — Orchestrator & API**
1. Tests: `/v1/chat` emits valid `StreamEvent` NDJSON, `/v1/status` states, memory endpoints, client cancel stops generation.
2. Implement orchestrator + API.

**Step 4 — Web app integration**
1. `src/ai/zenoBrain.ts` provider + tests in the existing Node test suite; `AI_PROVIDER=zeno` in `.env.example`.
2. Launcher starts the Python brain; Ollama path kept as fallback until Boss retires it.

## 5. Key dependencies (to be pinned in Step 2)

`llama-cpp-python`, `chromadb`, `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `websockets` (edge client); dev: `pytest`, `pytest-asyncio`, `httpx`, `ruff`, `mypy`. Python 3.11+.

## 6. Decisions (approved by Boss, 2026-10-19)

1. **Engine:** llama-cpp-python. Grammar-constrained JSON is required for ReAct tool calls.
2. **Memory store:** ChromaDB (embedded).
3. **Hardware:** CPU inference on the development machine. The project will later move to an NVIDIA laptop, so the CUDA wheel swap is documented in `brain/CLAUDE.md` and scripted in `brain/setup.ps1 -Cuda` / `brain/setup.sh --cuda`.
4. **Edge devices:** WebSocket server bound to localhost only in v1. LAN + TLS is v1.1.
5. **Tool permissions:** as proposed (named tools, curated scripts folder, confirmation for state changes).
