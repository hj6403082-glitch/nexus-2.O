"""Single source of configuration: ``ZENO_*`` environment variables and ``brain/.env``."""

from pathlib import Path

from pydantic import Field
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
