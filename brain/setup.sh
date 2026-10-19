#!/usr/bin/env bash
# Creates brain/.venv and installs Zeno's brain dependencies (Linux, macOS, Raspberry Pi).
#   ./setup.sh                       CPU build (default)
#   ./setup.sh --cuda [cu121..cu125] NVIDIA GPU build, prebuilt wheel (default cu124)
#   ./setup.sh --cuda-source         compile against the installed CUDA Toolkit
set -euo pipefail
cd "$(dirname "$0")"

LLAMA="llama-cpp-python==0.3.36"
MODE="cpu"; CUDA_VERSION="cu124"
case "${1:-}" in
  --cuda) MODE="cuda"; CUDA_VERSION="${2:-cu124}" ;;
  --cuda-source) MODE="cuda-source" ;;
  "") ;;
  *) echo "usage: $0 [--cuda [cu121|cu122|cu123|cu124|cu125] | --cuda-source]" >&2; exit 2 ;;
esac

[ -x .venv/bin/python ] || python3 -m venv .venv
PY=.venv/bin/python
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements-dev.txt

if [ "$MODE" = "cuda" ]; then
  "$PY" -m pip install --force-reinstall --no-deps --no-cache-dir "$LLAMA" \
    --index-url "https://abetlen.github.io/llama-cpp-python/whl/$CUDA_VERSION" \
    --extra-index-url https://pypi.org/simple
elif [ "$MODE" = "cuda-source" ]; then
  CMAKE_ARGS="-DGGML_CUDA=on" "$PY" -m pip install --force-reinstall --no-deps --no-cache-dir \
    --no-binary llama-cpp-python "$LLAMA"
fi

"$PY" -c "import llama_cpp; print('llama.cpp', llama_cpp.__version__, '| GPU offload:', llama_cpp.llama_supports_gpu_offload())"
echo "Done. Activate with: source .venv/bin/activate   then run: pytest"
