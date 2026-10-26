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
    log_file: Path = Path("data/logs/zeno.log")
    """Where logs go when there is no console (pythonw, the Windows logon task)."""
    scripts_dir: Path = Path("scripts")
    """Owner-curated Python scripts the agent may run (with approval), by name."""
    script_timeout: float = Field(30.0, gt=0.0)
    script_max_output: int = Field(4000, ge=100)

    api_token_file: Path = Path("data/api-token")
    """Bearer token for the chat socket; created on first start, readable only by you."""
    api_allowed_origins: list[str] = []
    """Browser origins allowed to open the chat socket. Empty: no browser pages."""
    chat_max_chars: int = Field(4000, ge=1)
    chat_max_context_chars: int = Field(8000, ge=0)
    """What the web app shows on screen, sent with each message (prompt only, never stored)."""

    # Phase 2 tools. Each reaches outside this PC, so each is off until configured.
    network_tools: bool = False
    """Offer ping, DNS lookup, single-port check and interface status."""
    web_search_url: str | None = None
    """Base URL of your SearXNG instance (JSON output enabled); None: no web search."""
    web_fetch: bool = False
    """Let the agent read web pages (public addresses only)."""
    web_fetch_allow_lan: bool = False
    """Also allow pages on your private network (never this PC itself)."""
    web_fetch_max_bytes: int = Field(2_000_000, ge=1024)
    web_fetch_timeout: float = Field(10.0, gt=0.0)
    ssh_hosts_file: Path = Path("data/ssh_hosts.json")
    """Machines ssh_run may reach; no file, no tool. Needs a known_hosts file."""
    ssh_command_timeout: float = Field(20.0, gt=0.0)
    ssh_max_output: int = Field(4000, ge=100)
    mqtt_file: Path = Path("data/mqtt.json")
    """Broker, readable topics and actuators; no file, no MQTT."""

    # Phase 3: OS integration (Linux and Windows; ZENO_OS_INTEGRATION.md).
    os_tools: bool = False
    """Offer telemetry (health, temperatures, processes), desktop notifications and
    service status for this OS."""
    run_command: bool = False
    """Offer run_command (Linux, no shell) or run_powershell (Windows, checked and
    constrained): one command at a time, your approval every time."""
    run_command_roots: list[Path] = [Path("~")]
    """Folders a command's working folder must be inside."""
    run_command_timeout: float = Field(30.0, ge=1.0, le=120.0)
    run_command_max_output: int = Field(4000, ge=100)
    """Characters kept from each of stdout and stderr."""
    desktop_notify_per_hour: int = Field(30, ge=1)

    @field_validator("web_search_url")
    @classmethod
    def _web_address(cls, url: str | None) -> str | None:
        if url is not None and not url.startswith(("http://", "https://")):
            raise ValueError("web_search_url must start with http:// or https://")
        return url

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
