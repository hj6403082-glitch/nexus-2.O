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


def test_agent_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.agent_max_steps == 5
    assert settings.agent_max_identical_calls == 2
    assert settings.agent_approval_timeout == 120.0
    assert settings.agent_max_observation_chars == 2000
    assert settings.audit_log_path == Path("data/audit/agent.jsonl")


def test_agent_limits_come_from_settings() -> None:
    from zeno.agent.loop import AgentLimits

    limits = AgentLimits.from_settings(Settings(_env_file=None, agent_max_steps=3))
    assert limits.max_steps == 3
    assert limits.max_identical_calls == 2


def test_agent_step_limit_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, agent_max_steps=0)


def test_orchestrator_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.api_token_file == Path("data/api-token")
    assert settings.api_allowed_origins == []
    assert settings.scripts_dir == Path("scripts")
    assert settings.script_timeout == 30.0
    assert settings.script_max_output == 4000
    assert settings.chat_max_chars == 4000
    assert settings.chat_max_context_chars == 8000


def test_the_env_example_loads_as_is() -> None:
    example = Path(__file__).parents[1] / ".env.example"
    settings = Settings(_env_file=example)
    assert settings.web_search_url is None and not settings.network_tools


# --- Multimodal switches: Boss's .env names map onto the settings the daemon reads ---


def test_multimodal_env_names_map_to_the_worker_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "ZENO_VISION_ENABLED": "true",
        "ZENO_VISION_HANDLER": "moondream",
        "ZENO_VISION_MODEL_PATH": "models/vision/moondream2-text-model-f16.gguf",
        "ZENO_VISION_MMPROJ_PATH": "models/vision/moondream2-mmproj-f16.gguf",
        "ZENO_VOICE_ENABLED": "true",
        "ZENO_STT_ENGINE": "faster-whisper",
        "ZENO_STT_MODEL": "base.en",
        "ZENO_STT_DEVICE": "cpu",
        "ZENO_STT_COMPUTE_TYPE": "int8",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    s = Settings(_env_file=None)
    assert s.vision is True
    assert s.vision_handler == "moondream"
    assert s.vision_model_path == Path("models/vision/moondream2-text-model-f16.gguf")
    assert s.vision_mmproj_path == Path("models/vision/moondream2-mmproj-f16.gguf")
    assert s.voice is True
    assert s.stt_engine == "faster-whisper"
    assert (s.stt_model, s.stt_device, s.stt_compute_type) == ("base.en", "cpu", "int8")


def test_multimodal_switches_also_take_the_short_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZENO_VISION", "true")
    monkeypatch.setenv("ZENO_VOICE", "false")
    s = Settings(_env_file=None)
    assert s.vision is True
    assert s.voice is False
    assert Settings(_env_file=None, vision=False, voice=True).vision is False


def test_an_unknown_stt_engine_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZENO_STT_ENGINE", "whisper-magic")
    with pytest.raises(ValueError, match="faster-whisper"):
        Settings(_env_file=None)


def test_the_example_env_file_loads_and_names_only_real_settings() -> None:
    example = Path(__file__).parents[1] / ".env.example"
    names = {
        line.split("=", 1)[0].lstrip("# ").strip()
        for line in example.read_text(encoding="utf-8").splitlines()
        if "=" in line and line.lstrip("# ").startswith("ZENO_")
    }
    known = {"ZENO_MQTT_PASSWORD"}  # read via mqtt.json's password_env, not Settings
    for name, field in Settings.model_fields.items():
        known.add(f"ZENO_{name.upper()}")
        alias = field.validation_alias
        if alias is not None:
            choices = getattr(alias, "choices", [alias])
            known.update(str(c).upper() for c in choices)
    assert names <= known, f"unknown settings in .env.example: {sorted(names - known)}"
    assert {"ZENO_VISION_ENABLED", "ZENO_VOICE_ENABLED", "ZENO_STT_ENGINE"} <= names
