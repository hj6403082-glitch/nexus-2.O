from pathlib import Path

import pytest

from tests.fixtures.tiny_gguf import write_tiny_gguf


@pytest.fixture(scope="session")
def tiny_gguf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real, few-hundred-KB GGUF with random weights (see tests/fixtures/tiny_gguf.py)."""
    return write_tiny_gguf(tmp_path_factory.mktemp("models") / "zeno-tiny.gguf")


@pytest.fixture(autouse=True)
def _ignore_the_owners_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never read brain/.env: on the owner's PC it switches real features on
    (OS tools, voice, ...), which would make results depend on whose machine runs them."""
    from zeno.config import Settings

    monkeypatch.setitem(Settings.model_config, "env_file", None)
