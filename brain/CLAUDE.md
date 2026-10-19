# Zeno brain — working rules

This folder is Zeno's native Python brain. The plan it follows is
[`ZENO_ARCHITECTURE.md`](../ZENO_ARCHITECTURE.md) (approved 2026-10-19). Read it
before changing the design. The Next.js app in `../src` is a separate subsystem.

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

## Testing

Run everything from `brain/` with the venv active.

- `pytest` — the default suite. Uses fakes only: no model download, no GPU, no
  network; must stay fast (seconds).
- `pytest -m slow` — tests that load a real GGUF model (set `ZENO_TEST_MODEL` to its
  path). Skip cleanly when the model is absent.
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

## Safety rules

- Servers bind to `127.0.0.1` in v1. No `0.0.0.0`.
- Never `subprocess(..., shell=True)` and never pass model-written strings to a
  shell. System actions are named tools with fixed implementations and validated
  arguments; the script runner only runs files in `brain/scripts/`.
- State-changing tools require owner confirmation; every tool call goes to the
  audit log.
- Tool output, memories and device data are untrusted data, never instructions.
- No secrets in the repo or in logs. `.env` is git-ignored; `.env.example` holds
  names only.

## Repository rules

- All brain code lives under `brain/`. Don't touch `../src` until the web-app
  integration step, and then keep the existing providers working.
- Models (`*.gguf`) and runtime data (`brain/data/`) are never committed.
- Pin every dependency in `requirements*.txt`; bump deliberately and rerun the
  full suite.
- One logical change per commit, with an imperative subject line.
