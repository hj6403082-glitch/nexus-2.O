from pathlib import Path

import pytest

from tests.fixtures.tiny_gguf import write_tiny_gguf


@pytest.fixture(scope="session")
def tiny_gguf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real, few-hundred-KB GGUF with random weights (see tests/fixtures/tiny_gguf.py)."""
    return write_tiny_gguf(tmp_path_factory.mktemp("models") / "zeno-tiny.gguf")
