"""Step 2 gate: the virtual environment has everything the four pillars need."""

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


@pytest.mark.parametrize("banned", ["langchain", "llama_index", "ollama"])
def test_banned_frameworks_are_not_installed(banned: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(banned)
