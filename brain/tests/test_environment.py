"""Step 2 gates: the virtual environment has everything the pillars and Phase 2 need."""

import importlib
import sys

import pytest

import zeno


def test_python_version_is_supported() -> None:
    assert sys.version_info >= (3, 11)


def test_package_exposes_version() -> None:
    assert zeno.__version__ == "0.1.0"


@pytest.mark.parametrize(
    "module",
    ["llama_cpp", "chromadb", "fastapi", "uvicorn", "websockets", "pydantic", "pydantic_settings"],
)
def test_runtime_dependency_imports(module: str) -> None:
    importlib.import_module(module)


# Phase 2 (ZENO_PHASE2_ARCHITECTURE.md section 7): tools, watchers, vision intake, voice.
@pytest.mark.parametrize(
    "module",
    [
        "PIL",  # vision intake
        "numpy",  # audio buffers
        "pywhispercpp",  # speech-to-text (whisper.cpp)
        "piper",  # text-to-speech
        "onnxruntime",  # Piper's runtime
        "webrtcvad",  # voice activity detection
        "psutil",  # watchers, network_status
        "icmplib",  # ping without a subprocess
        "httpx",  # web_search, fetch_page
        "selectolax",  # HTML to text
        "asyncssh",  # ssh_run
        "aiomqtt",  # MQTT sense and actuation
    ],
)
def test_phase2_dependency_imports(module: str) -> None:
    importlib.import_module(module)


def test_llama_cpp_ships_the_vision_handlers() -> None:
    # Vision needs no new package: the planned handlers come with llama-cpp-python.
    from llama_cpp import llama_chat_format

    for handler in ("MoondreamChatHandler", "Qwen25VLChatHandler", "MTMDChatHandler"):
        assert hasattr(llama_chat_format, handler)


def test_pytorch_is_not_pulled_in() -> None:
    # Every Phase 2 model runs on llama.cpp, whisper.cpp or onnxruntime.
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("torch")


@pytest.mark.parametrize("banned", ["langchain", "llama_index", "ollama"])
def test_banned_frameworks_are_not_installed(banned: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(banned)


@pytest.mark.skipif(sys.platform != "linux", reason="dbus-fast is installed on Linux only")
@pytest.mark.parametrize("module", ["dbus_fast", "dbus_fast.aio"])
def test_phase3_linux_dependency_imports(module: str) -> None:
    importlib.import_module(module)


def test_property_testing_is_available() -> None:
    importlib.import_module("hypothesis")
