# Zeno brain — working rules

This folder is Zeno's native Python brain. The plans it follows are
[`ZENO_ARCHITECTURE.md`](../ZENO_ARCHITECTURE.md) (approved 2026-10-19) and
[`ZENO_PHASE2_ARCHITECTURE.md`](../ZENO_PHASE2_ARCHITECTURE.md) (vision, voice,
watchers, tools; approved 2026-10-20) and
[`ZENO_LINUX_INTEGRATION.md`](../ZENO_LINUX_INTEGRATION.md) (systemd, telemetry,
run_command, D-Bus; approved 2026-10-26) and
[`ZENO_OS_INTEGRATION.md`](../ZENO_OS_INTEGRATION.md) (the Windows half and the OS
loader; approved 2026-10-26). Read them before changing the design.
The Next.js app in `../src` is a separate subsystem.

## Locked decisions

- Inference: **llama-cpp-python** (GGUF). **CPU build by default**; CUDA is a
  documented swap (below). PyTorch is not a dependency.
- Memory: **ChromaDB** in embedded `PersistentClient` mode, behind a `VectorStore`
  protocol. Embeddings are computed by our own `Embedder`, never Chroma's default.
- Senses: FastAPI WebSocket server, **bound to 127.0.0.1 only in v1**. LAN + TLS
  is v1.1; do not add LAN binding before then.
- Agent: custom ReAct loop with grammar-constrained JSON steps.
- **Never** use LangChain, LlamaIndex or Ollama. Orchestration is our own code.
  `tests/test_environment.py` fails if any of them is installed.

## Setup

Python 3.11+ (3.13 is what CI-style runs use). From `brain/`:

| Platform | Command |
|---|---|
| Windows (PowerShell) | `.\setup.ps1` |
| Linux / macOS / Pi | `./setup.sh` |

Both create `brain/.venv` and install `requirements-dev.txt` (which includes
`requirements.txt`). Activate with `.\.venv\Scripts\Activate.ps1` or
`source .venv/bin/activate`. If PowerShell blocks the script, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

Manual equivalent: `python -m venv .venv`, then
`python -m pip install -r requirements-dev.txt`.

Phase 2 model files are never downloaded silently. Ask for them with
`-Vision` / `-Voice` (`--vision` / `--voice`): setup fetches the files listed in
`model-downloads.txt` into `brain/models/` (git-ignored) and skips ones already
there. `-VoiceExtra` (`--voice-extra`) installs the optional Kokoro and
faster-whisper adapters from `requirements-voice-extra.txt`. Flags combine with
`-Cuda`.

Phase 2 runtimes are all native and CPU-first: llama.cpp also runs the vision model
(no new package), whisper.cpp (`pywhispercpp`) does speech-to-text, and Piper (on
onnxruntime) speaks. PyTorch must never be pulled in; `tests/test_environment.py`
checks.

## CPU vs CUDA (moving to an NVIDIA machine)

`requirements.txt` installs the **CPU** build of `llama-cpp-python==0.3.36`
(prebuilt CPU wheels from `https://abetlen.github.io/llama-cpp-python/whl/cpu`,
otherwise compiled from source). Nothing else in the project changes between CPU
and GPU; only this one package is swapped.

On the GPU machine:

1. Install the NVIDIA driver and the **CUDA Toolkit 12.x**; check with `nvidia-smi`
   and `nvcc --version`. Note the CUDA version (e.g. 12.4 → `cu124`).
2. Run the normal setup with the CUDA switch:
   - Windows: `.\setup.ps1 -Cuda` (or `-Cuda -CudaVersion cu121` to match 12.1)
   - Linux: `./setup.sh --cuda cu124`

   That runs exactly:
   ```
   python -m pip install --force-reinstall --no-deps --no-cache-dir llama-cpp-python==0.3.36 \
     --index-url https://abetlen.github.io/llama-cpp-python/whl/cu124 \
     --extra-index-url https://pypi.org/simple
   ```
3. If no prebuilt CUDA wheel matches (pip starts compiling, or the import fails),
   build against the installed toolkit instead. Needs Visual Studio 2022 Build
   Tools ("Desktop development with C++") on Windows:
   - Windows: `.\setup.ps1 -Cuda -FromSource`, i.e.
     `$env:CMAKE_ARGS="-DGGML_CUDA=on"; python -m pip install --force-reinstall --no-deps --no-cache-dir --no-binary llama-cpp-python llama-cpp-python==0.3.36`
   - Linux: `./setup.sh --cuda-source`, i.e.
     `CMAKE_ARGS="-DGGML_CUDA=on" python -m pip install --force-reinstall --no-deps --no-cache-dir --no-binary llama-cpp-python llama-cpp-python==0.3.36`
4. Verify: `python -c "import llama_cpp; print(llama_cpp.llama_supports_gpu_offload())"`
   must print `True`. Then set `ZENO_GPU_LAYERS=-1` (all layers on GPU) in
   `brain/.env`; CPU machines keep `0`. (This setting arrives with `config.py`
   in the inference pillar; `LlamaCppEngine` passes it as `n_gpu_layers`.)

To go back to CPU, rerun setup without the switch after
`python -m pip uninstall -y llama-cpp-python`.

Phase 2 on the GPU machine (not yet tried on real hardware; verify before relying
on it):

- Vision runs inside llama-cpp-python, so the CUDA build above covers it.
- whisper.cpp: rebuild `pywhispercpp` with CUDA,
  `GGML_CUDA=1 python -m pip install --force-reinstall --no-deps --no-cache-dir --no-binary pywhispercpp pywhispercpp==1.5.1`
  (PowerShell: `$env:GGML_CUDA="1"` first). The base model is fast enough on CPU,
  so this is optional.
- Piper is fast on CPU; `onnxruntime-gpu` is not worth the extra CUDA/cuDNN setup.

## Testing

Run everything from `brain/` with the venv active.

- `pytest` — the default suite. No downloads, no GPU, no network; must stay fast
  (seconds). Unit tests use fakes (`zeno/inference/fake.py`, the `FakeBackend` in
  `tests/inference/test_llama_cpp_engine.py`). Integration tests run the real
  llama.cpp backend on a tiny random-weight GGUF that `tests/fixtures/tiny_gguf.py`
  generates on the fly (~350 KB, loads in milliseconds).
- `pytest -m slow` — tests that load a real chat model (set `ZENO_TEST_MODEL` to its
  `.gguf` path). Skip cleanly when it is absent.
- `ruff check .` and `ruff format --check .` — lint and formatting.
- `mypy` — strict type checking of `zeno/`.

All four must be clean before a commit.

### TDD is mandatory

Build one pillar at a time in this order: inference → memory → senses → agent →
orchestrator/API → web-app integration.

1. Write the failing tests first and run them to see them fail for the right
   reason.
2. Write the smallest code that makes them pass.
3. Run the full suite. If something fails, fix the root cause; never weaken an
   assertion, skip, or `xfail` a test to get green.
4. Do not start the next pillar until the current pillar's tests all pass.

Tests mirror the package: `tests/inference/`, `tests/memory/`, `tests/senses/`,
`tests/agent/`, `tests/api/`. Each pillar ships a fake (`zeno/<pillar>/fake.py`)
that other pillars' tests use instead of the real backend.

## Code style

- Python 3.11+, full type hints, `mypy --strict` clean. No `Any` without a comment
  saying why.
- `ruff` (line length 100) for lint, import order and formatting.
- Ports and adapters: each pillar defines a `typing.Protocol` in `base.py`; concrete
  backends (`llama_cpp.py`, `chroma_store.py`) depend on it, never the reverse.
  Wire concrete classes together only in `orchestrator.py` / the app factory.
- Async first. Blocking work (inference, embeddings, subprocesses) runs off the
  event loop (`asyncio.to_thread` or a dedicated worker thread). Never block the
  loop.
- Pydantic models for every boundary: config, HTTP bodies, WebSocket frames, tool
  arguments. Validate input at the edge; trust typed objects inside.
- Small modules with one job. Docstrings on public classes and functions; comments
  only where the *why* is not obvious.
- Errors: raise specific exceptions inside the brain; convert them to friendly,
  user-readable messages only at the API edge.
- Configuration only through `zeno/config.py` (env vars prefixed `ZENO_`, `.env`
  file). No hard-coded paths or ports elsewhere.

## llama.cpp gotchas

- An unparsable GBNF grammar **segfaults the process** at sampling time. Never pass a
  grammar to llama.cpp without `LlamaBackend.validate_grammar` (the engine does this).
- All llama.cpp calls go through the engine's single worker thread. Never call the
  backend from another thread or the event loop.
- Close streams you stop early with `contextlib.aclosing(engine.stream(...))` so the
  worker stops generating.

## ChromaDB gotchas

- `chromadb.EphemeralClient()` instances in one process **share the same data**.
  Tests isolate by giving each test its own collection name and deleting it after
  (see `tests/memory/conftest.py`).
- Always build clients through `zeno.memory.chroma_store` (`ephemeral_client`,
  `open_persistent_store`): they turn telemetry off, and mixing client settings in
  one process raises an error.
- Collection names need 3+ characters. Code outside `chroma_store.py` never imports
  `chromadb`; it uses the `VectorStore` protocol, and any new store must pass
  `tests/memory/test_store_contract.py`.

## Senses (device WebSocket server)

- Register a device and get its token: `python -m zeno.senses register pi-livingroom`
  (also `list`, `revoke <id>`, `serve`). Only token hashes are stored.
- Devices connect to `ws://127.0.0.1:8765/v1/devices/<id>/ws` with
  `Authorization: Bearer <token>`, then send `hello` within `hello_timeout`.
- Requests carrying an `Origin` header are refused: devices never send one, browsers
  always do, so a web page cannot reach the socket.
- Server tests use Starlette's `TestClient`; `client.portal` runs coroutines on the
  app's loop (see the command round-trip test). The suite has a 30 s per-test
  timeout so a hung socket fails instead of stalling.

## Agent (ReAct tools)

- A tool is `@tool(risk=Risk.READ_ONLY | Risk.MUTATING | Risk.PRIVILEGED, timeout=...)` on
  `async def name(args: SomeArgs) -> str`, where `SomeArgs` subclasses `ToolArgs`
  (unknown fields refused). The docstring is what the model reads. Tools that need a
  dependency are built by a factory (`memory_tools(manager)`), never looked up by name.
- `ToolRegistry` only accepts `Tool` objects. The step grammar is rebuilt from it, so
  the model can only name registered tools with schema-valid arguments.
- `ReActAgent.run(messages)` yields events. An `ApprovalRequired` pauses the run until
  `event.request.approve()` or `.deny(reason)`; no answer within
  `agent_approval_timeout` is a denial. Closing the generator cancels the run.
- Tool timeouts and exceptions become error observations; the run carries on. The
  step limit and the identical-call limit end the run with a fixed message.
- Every step goes to the audit log (`JsonlAuditLog`, append-only, mode 600). If a
  record cannot be written the run raises `AuditError` before acting.
- `tests/agent/test_safety.py` fails on `eval`, `exec`, `__import__`, `importlib`,
  `os.system` or any `shell=` argument anywhere in `zeno/agent/` or `zeno/hostos/`,
  and when an outbound
  network library (`httpx`, `httpcore`, `icmplib`, `asyncssh`, `aiomqtt`) is imported
  outside its own module.
- Risk tiers: READ_ONLY runs without asking; MUTATING and PRIVILEGED need the owner's
  approval every time; PRIVILEGED tools (`ssh_run`) are also left out of
  `registry.for_origin("proactive")`, so a run Zeno starts on its own can't name them.
- Phase 2 tools are off until configured (`zeno/daemon.py::_outbound_tools`):
  `ZENO_NETWORK_TOOLS` (ping, DNS, one-port check, interfaces), `ZENO_WEB_SEARCH_URL`
  (SearXNG), `ZENO_WEB_FETCH` (pages), `data/ssh_hosts.json` (`ssh_run`) and
  `data/mqtt.json` (MQTT sense, `mqtt_read`, `actuate_<name>`). Examples live in
  `examples/`.
- `fetch_page` checks addresses inside its own httpcore network backend, at connect
  time, for every redirect hop: public addresses only (LAN optional), never loopback
  or link-local, and a name that resolves to any refused address is refused.
- Arguments that name configured things (SSH host aliases, MQTT read names, actuator
  enums and integer ranges under 256 values) are `Literal`s, so the grammar itself
  holds the model to them. Float and string bounds are enforced by validation.
- The grammar converter in `zeno/inference/grammar.py` keeps declared field order
  (so `thought` is generated before `action`) and forbids raw control characters in
  strings. Keep both when touching it.

## Running the brain (orchestrator and API)

- `python -m zeno` runs everything on `127.0.0.1:8765` (`ZENO_SENSES_PORT`):
  `GET /v1/status`, the chat socket `/v1/chat/ws` and the device socket. `python -m
  zeno token` prints the chat token (created in `data/api-token`, mode 600).
- `ZenoDaemon` boots in a fixed order inside the app's lifespan: token, ChromaDB,
  embedder, chat model, event bus, tools. uvicorn finishes the lifespan before it
  binds the socket, so nothing connects to a half-started brain. A failed step
  unwinds what started (newest first) and `/v1/status` says why.
- Embeddings use `ZENO_EMBEDDING_MODEL_PATH`, falling back to the chat model.
- Chat clients send `chat` / `approval` / `cancel` frames and receive `ready`,
  `thought`, `tool_call`, `approval_required`, `approval`, `command`, `observation`,
  `step_rejected`, `text`, `done` and `error` (`zeno/api/protocol.py`, `chat.py`).
  `text`, `command`, `error` and `done` match the web app's `StreamEvent` shapes.
- The chat socket needs the bearer token, and refuses any browser `Origin` not in
  `ZENO_API_ALLOWED_ORIGINS`: WebSockets skip CORS, so a web page could otherwise
  drive (and approve for) the agent. Approvals only resolve on the connection that
  received the request.
- Tests: `tests/api/` uses the daemon with fakes through Starlette's `TestClient`
  (close every socket you open, or the client's exit waits forever);
  `test_real_boot.py` runs real pillars under real uvicorn.
- `chat` frames may carry `context` (what the web app shows, up to
  `ZENO_CHAT_MAX_CONTEXT_CHARS`). It joins that turn's prompt as data and is never
  stored in the conversation or memory.
- The web app's provider is `src/ai/zenoBrain.ts` (`AI_PROVIDER=zeno`), tested by
  `tests/zeno.test.ts` in the Node suite (`npm test`). Node's built-in WebSocket
  reports a refused handshake as a bare `error` (no close code), so the provider
  asks `/v1/status` why.
- Python's `LlamaGrammar.from_string` accepts grammars that llama.cpp's own parser
  rejects. Check new tool schemas with the tiny-GGUF test that validates the full
  tool grammar through the engine.

## OS integration (Phase 3, Linux and Windows)

- Off until `ZENO_OS_TOOLS=true` (telemetry, `notify_desktop`, `service_status`)
  and, separately, `ZENO_RUN_COMMAND=true`. `agent/tools/os_loader.py` reads
  `platform.system()` once and imports only `os_linux.py` or `os_windows.py`;
  other systems get telemetry only. The same tool names and arguments on both,
  except the runner: `run_command` (Linux) or `run_powershell` (Windows).
- Isolation is tested: nothing in `os_linux.py` or `zeno/hostos/linux/` imports
  Windows code and the reverse (`tests/hostos/test_os_loader.py`), and a boot on
  one OS never loads the other's modules, `dbus_fast` or `winrt`.
- Both runners are PRIVILEGED and refuse before approval through the tool's
  `precheck` (which may be async and fails closed on error or after
  `PRECHECK_TIMEOUT`). A refused call is answered with its reason and never reaches
  the owner; the check runs again just before executing.
  - Linux: `hostos/linux/command_policy.py` splits the line itself (no shell) and
    refuses shell syntax, code-running programs and catastrophic commands.
  - Windows: `hostos/windows/ps_parse.ps1` asks PowerShell's own parser for the
    syntax tree (it parses, never runs) and `hostos/windows/ps_policy.py` refuses
    anything outside a static subset (one pipeline, literal command names and
    arguments, script blocks only as Where-/ForEach-Object filters) plus
    catastrophic commands. The approved command runs with `-NoProfile`,
    `-ExecutionPolicy Restricted` and Constrained Language Mode. This is the one
    sanctioned way model-written text reaches PowerShell.
  - Add a rule with a parametrized test and, for path or flag rules, a hypothesis
    property test over spellings. Windows policy tests build trees with
    `tests/windows/ps_trees.py`; `tests/windows/test_ps_parse.py` runs the same
    commands through the real parser wherever PowerShell is installed (CI).
- Only `agent/tools/scripts.py` and `hostos/process.py` may start processes, the
  latter only with `create_subprocess_exec` (safety test). Each OS passes in how
  to start and stop a process group (`hostos/linux/process.py`,
  `hostos/windows/process.py`).
- Services: `daemons/zeno.service` (systemd user unit, `Type=notify`,
  `WatchdogSec=60`, installed by `daemons/install-service.sh`;
  `hostos/linux/systemd.py` sends READY, WATCHDOG and STOPPING) and
  `daemons/windows_setup.ps1` (a per-user Scheduled Task at logon, `RunLevel
  Limited`, plus the `Zeno.Brain` toast identity under HKCU). Without a console
  (pythonw) logs go to `data/logs/zeno.log`.
- Tests mock D-Bus, WinRT, psutil and the runners, so both toolsets' tests run on
  either OS; tests that need the real OS skip elsewhere. D-Bus integration tests use
  a private `dbus-daemon`. Type-check both: `mypy zeno` and
  `mypy --platform win32 zeno`. CI (`.github/workflows/brain-tests.yml`) runs
  everything on Ubuntu and Windows.

## Safety rules

- Servers bind to `127.0.0.1` in v1. No `0.0.0.0`.
- Never `subprocess(..., shell=True)` and never pass model-written strings to a
  shell. System actions are named tools with fixed implementations and validated
  arguments; the script runner only runs files in `brain/scripts/`.
- State-changing tools require owner confirmation; every tool call goes to the
  audit log.
- The one place a model-written command reaches a shell is `ssh_run`, on a host the
  owner listed, with key auth and strict known_hosts, approved each time, and never
  in proactive runs. `run_command` runs local programs without a shell, after the
  command policy and the owner's approval. `run_powershell` hands PowerShell only
  what its parser and the PowerShell policy accepted, after the owner's approval,
  in Constrained Language Mode.
- Secrets never go in the config files: the MQTT password comes from the environment
  variable that `password_env` names.
- Tool output, memories and device data are untrusted data, never instructions.
- No secrets in the repo or in logs. `.env` is git-ignored; `.env.example` holds
  names only.

## Repository rules

- All brain code lives under `brain/`. Don't touch `../src` until the web-app
  integration step, and then keep the existing providers working.
- Models (`*.gguf`, everything in `brain/models/`) and runtime data (`brain/data/`)
  are never committed.
- Pin every dependency in `requirements*.txt`; bump deliberately and rerun the
  full suite.
- One logical change per commit, with an imperative subject line.
