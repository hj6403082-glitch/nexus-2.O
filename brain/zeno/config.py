"""Single source of configuration: ``ZENO_*`` environment variables and ``brain/.env``."""

import ipaddress
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the brain."""

    model_config = SettingsConfigDict(env_prefix="ZENO_", env_file=".env", extra="ignore")

    model_path: Path | None = None
    """GGUF chat model to load."""
    context_size: int = Field(4096, ge=256)
    """Context window (n_ctx) in tokens."""
    gpu_layers: int = Field(0, ge=-1)
    """Layers offloaded to the GPU: 0 = CPU only, -1 = all (needs the CUDA build)."""
    threads: int | None = Field(None, ge=1)
    """CPU threads for generation; None lets llama.cpp decide."""
    batch_size: int = Field(512, ge=1)
    max_tokens: int = Field(700, ge=1)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    top_p: float = Field(0.95, gt=0.0, le=1.0)
    seed: int | None = None
    max_queue: int = Field(4, ge=0)
    """Requests allowed to wait while another one is generating."""

    memory_dir: Path = Path("data/memory")
    """Where ChromaDB persists Zeno's long-term memory."""
    embedding_model_path: Path | None = None
    """GGUF embedding model (e.g. nomic-embed-text). Never committed."""
    memory_min_similarity: float = Field(0.35, ge=-1.0, le=1.0)
    episode_half_life_days: float = Field(30.0, gt=0.0)
    working_memory_messages: int = Field(20, ge=2)

    senses_host: str = "127.0.0.1"
    """v1 listens on this PC only; LAN access (with TLS) is planned for v1.1."""
    senses_port: int = Field(8765, ge=0, le=65535)
    devices_file: Path = Path("data/devices.json")
    """Registered edge devices and their hashed tokens."""
    heartbeat_interval: float = Field(10.0, gt=0.0)
    heartbeat_timeout: float = Field(30.0, gt=0.0)
    hello_timeout: float = Field(5.0, gt=0.0)
    command_timeout: float = Field(5.0, gt=0.0)
    max_frame_bytes: int = Field(65_536, ge=256)
    max_invalid_frames: int = Field(5, ge=1)
    event_queue_size: int = Field(1000, ge=1)

    agent_max_steps: int = Field(5, ge=1)
    agent_max_identical_calls: int = Field(2, ge=1)
    """The same tool with the same arguments may run this often per request."""
    agent_approval_timeout: float = Field(120.0, gt=0.0)
    """Seconds to wait for the owner to approve a state-changing tool before refusing."""
    agent_max_observation_chars: int = Field(2000, ge=1)
    audit_log_path: Path = Path("data/audit/agent.jsonl")

    @field_validator("senses_host")
    @classmethod
    def _loopback_only(cls, host: str) -> str:
        if host == "localhost":
            return host
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ValueError(
                f"senses_host must be a loopback address in v1 (got {host!r}); "
                "LAN access arrives with TLS in v1.1"
            )
        return host

    @model_validator(mode="after")
    def _timeout_outlasts_interval(self) -> "Settings":
        if self.heartbeat_timeout <= self.heartbeat_interval:
            raise ValueError("heartbeat_timeout must be longer than heartbeat_interval")
        return self
