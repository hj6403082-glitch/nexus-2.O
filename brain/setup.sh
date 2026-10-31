#!/usr/bin/env bash
# Creates brain/.venv and installs Zeno's brain dependencies (Linux, macOS, Raspberry Pi).
#   ./setup.sh                       CPU build (default)
#   ./setup.sh --cuda [cu121..cu125] NVIDIA GPU build, prebuilt wheel (default cu124)
#   ./setup.sh --cuda-source         compile against the installed CUDA Toolkit
#   ./setup.sh --vision              also download the vision model files into models/
#   ./setup.sh --voice               also download the speech-to-text and voice files
#   ./setup.sh --voice-extra         also install the optional Kokoro / faster-whisper adapters
# Flags combine, e.g. ./setup.sh --cuda cu124 --vision --voice
set -euo pipefail
cd "$(dirname "$0")"

LLAMA="llama-cpp-python==0.3.36"
MODE="cpu"; CUDA_VERSION="cu124"; WANT=(); VOICE_EXTRA=0
usage() { echo "usage: $0 [--cuda [cu121..cu125] | --cuda-source] [--vision] [--voice] [--voice-extra]" >&2; exit 2; }
while [ $# -gt 0 ]; do
  case "$1" in
    --cuda) MODE="cuda"; if [[ "${2:-}" =~ ^cu12[1-5]$ ]]; then CUDA_VERSION="$2"; shift; fi ;;
    --cuda-source) MODE="cuda-source" ;;
    --vision) WANT+=(vision) ;;
    --voice) WANT+=(voice) ;;
    --voice-extra) VOICE_EXTRA=1 ;;
    *) usage ;;
  esac
  shift
done

[ -x .venv/bin/python ] || python3 -m venv .venv
PY=.venv/bin/python
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements-dev.txt
if [ "$VOICE_EXTRA" = 1 ]; then "$PY" -m pip install -r requirements-voice-extra.txt; fi

if [ "$MODE" = "cuda" ]; then
  "$PY" -m pip install --force-reinstall --no-deps --no-cache-dir "$LLAMA" \
    --index-url "https://abetlen.github.io/llama-cpp-python/whl/$CUDA_VERSION" \
    --extra-index-url https://pypi.org/simple
elif [ "$MODE" = "cuda-source" ]; then
  CMAKE_ARGS="-DGGML_CUDA=on" "$PY" -m pip install --force-reinstall --no-deps --no-cache-dir \
    --no-binary llama-cpp-python "$LLAMA"
fi

# Model files are only fetched when asked for, from the list in model-downloads.txt.
if [ ${#WANT[@]} -gt 0 ]; then
  mkdir -p models
  while read -r group name url; do
    case "$group" in ''|\#*) continue ;; esac
    [[ " ${WANT[*]} " == *" $group "* ]] || continue
    # One folder per kind (models/vision, models/voice), matching .env.example.
    target="models/$group/$name"
    mkdir -p "models/$group"
    if [ ! -e "$target" ] && [ -e "models/$name" ]; then mv "models/$name" "$target"; fi
    if [ -s "$target" ]; then echo "have   $target"; continue; fi
    echo "fetch  $target"
    curl -fL --retry 3 -o "$target.part" "$url" && mv "$target.part" "$target"
  done < model-downloads.txt
fi

"$PY" -c "import llama_cpp; print('llama.cpp', llama_cpp.__version__, '| GPU offload:', llama_cpp.llama_supports_gpu_offload())"
echo "Done. Activate with: source .venv/bin/activate   then run: pytest"
