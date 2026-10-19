from pathlib import Path

import pytest
from pydantic import ValidationError

from zeno.config import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ZENO_MODEL_PATH", "ZENO_GPU_LAYERS", "ZENO_CONTEXT_SIZE", "ZENO_THREADS"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_target_cpu_inference() -> None:
    settings = Settings(_env_file=None)
    assert settings.model_path is None
    assert settings.gpu_layers == 0
    assert settings.context_size == 4096
    assert settings.max_tokens == 700
    assert settings.max_queue == 4


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    monkeypatch.setenv("ZENO_MODEL_PATH", str(model))
    monkeypatch.setenv("ZENO_GPU_LAYERS", "-1")
    monkeypatch.setenv("ZENO_CONTEXT_SIZE", "8192")
    settings = Settings(_env_file=None)
    assert settings.model_path == model
    assert settings.gpu_layers == -1
    assert settings.context_size == 8192


def test_reads_dotenv_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("ZENO_GPU_LAYERS=20\nZENO_THREADS=6\n")
    settings = Settings(_env_file=env)
    assert settings.gpu_layers == 20
    assert settings.threads == 6


@pytest.mark.parametrize(
    ("field", "value"),
    [("gpu_layers", -2), ("context_size", 64), ("max_tokens", 0), ("temperature", -0.1)],
)
def test_rejects_invalid_values(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_memory_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.memory_dir == Path("data/memory")
    assert settings.embedding_model_path is None
    assert settings.memory_min_similarity == 0.35
    assert settings.episode_half_life_days == 30.0
    assert settings.working_memory_messages == 20
