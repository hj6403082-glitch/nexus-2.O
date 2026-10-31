"""Single source of configuration: ``ZENO_*`` environment variables and ``brain/.env``."""

import ipaddress
from pathlib import Path
from typing import Literal

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

    # J.A.R.V.I.S. Protocol: the always-on Windows daemon (ZENO_GOD_MODE_WINDOWS.md).
    wakeword: bool = True
    """Listen for "Hey Zeno" on the microphone (Windows daemon). On by default."""
    wakeword_model_path: Path | None = None
    """The openwakeword .onnx model. Blank uses the listener's built-in default."""
    wakeword_confidence: float = Field(0.6, ge=0.0, le=1.0)
    """How sure the model must be before a "wake" event fires."""

    # Multimodal layer: sight and voice workers (ZENO_MULTIMODAL_ARCH.md).
    vision: bool = False
    """Offer analyze_vision_frame. Needs a vision model (vision_model_path + mmproj)."""
    vision_model_path: Path | None = None
    """The vision model's .gguf (e.g. Moondream2)."""
    vision_mmproj_path: Path | None = None
    """The matching image projector .gguf (mmproj)."""
    vision_handler: Literal["moondream", "llava", "mtmd"] = "moondream"
    vision_context_size: int = Field(2048, ge=512)
    vision_max_tokens: int = Field(200, ge=1, le=2000)
    vision_max_side: int = Field(768, ge=64, le=4096)
    """Images are downscaled to at most this many pixels on the long side."""
    vision_max_pixels: int = Field(40_000_000, ge=4096)
    """Images with more pixels are refused before decoding (decompression bombs)."""
    vision_timeout: float = Field(60.0, gt=0.0)
    vision_queue_size: int = Field(4, ge=1)
    frame_ttl: float = Field(60.0, gt=0.0)
    """Seconds an image stays available to the vision tool. Never written to disk."""
    frame_max_bytes: int = Field(4 * 1024 * 1024, ge=1024)
    frame_store_max_bytes: int = Field(32 * 1024 * 1024, ge=1024)

    voice: bool = True
    """After "Hey Zeno", transcribe the command and answer out loud. Stays off until the
    speech engines are installed (faster-whisper, a Piper voice)."""
    stt_model: str = "base.en"
    """faster-whisper model name or folder."""
    stt_device: Literal["cpu", "cuda"] = "cpu"
    stt_compute_type: str = "int8"
    tts_voice_path: Path | None = None
    """The Piper voice (.onnx, with its .onnx.json beside it)."""
    vad_aggressiveness: int = Field(2, ge=0, le=3)
    vad_silence_ms: int = Field(800, ge=100, le=5000)
    """This much silence after speech ends the command."""
    voice_no_speech_s: float = Field(5.0, gt=0.0)
    """Give up when nothing is said this long after the wake word."""
    voice_max_utterance_s: float = Field(15.0, gt=0.0, le=60.0)
    audio_in_queue_size: int = Field(256, ge=1)
    audio_out_queue_size: int = Field(32, ge=1)
    speak_chat_answers: bool = False
    """Also speak answers to typed chat messages (voice commands are always spoken)."""
    model_idle_unload: float = Field(600.0, gt=0.0)
    """Seconds a vision or speech model stays loaded without work before it is freed."""

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
