"""The device wire protocol: versioned JSON frames, validated strictly at the edge.

Every frame is ``{"v": 1, "id": ..., "type": ..., ...}``. Devices may only send the
inbound types; commands only ever flow from the brain to a device.
"""

import json
import time
import uuid
from enum import IntEnum
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)

from zeno.senses.events import DeviceEvent, EventKind

PROTOCOL_VERSION = 1

FrameId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
Capability = Annotated[
    str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$", max_length=64)
]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_.]{1,64}$")]
Text = Annotated[str, StringConstraints(max_length=256)]
Scalar = StrictBool | StrictInt | StrictFloat | Text
Number = StrictInt | StrictFloat


class CloseCode(IntEnum):
    NORMAL = 1000
    GOING_AWAY = 1001
    POLICY = 1008
    REPLACED = 4000
    HELLO_TIMEOUT = 4001
    HEARTBEAT_TIMEOUT = 4002


class ProtocolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _Frame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    v: Literal[1] = 1
    id: FrameId = Field(default_factory=lambda: uuid.uuid4().hex)


# Device -> brain


class Hello(_Frame):
    type: Literal["hello"] = "hello"
    capabilities: list[Capability] = Field(default_factory=list, max_length=32)


class Telemetry(_Frame):
    type: Literal["telemetry"] = "telemetry"
    metrics: dict[Key, Scalar] = Field(max_length=64)


class SensorUpdate(_Frame):
    type: Literal["sensor"] = "sensor"
    sensor: Capability
    value: Scalar | Annotated[list[Number], Field(max_length=64)]
    unit: Text | None = None


class Ping(_Frame):
    type: Literal["ping"] = "ping"


class Pong(_Frame):
    type: Literal["pong"] = "pong"


class CommandResult(_Frame):
    type: Literal["result"] = "result"
    command_id: FrameId
    ok: StrictBool
    detail: Text = ""
    data: dict[Key, Scalar] = Field(default_factory=dict, max_length=64)


# Brain -> device


class Welcome(_Frame):
    type: Literal["welcome"] = "welcome"
    heartbeat_interval: float


class Command(_Frame):
    type: Literal["command"] = "command"
    action: Capability
    args: dict[Key, Scalar | Annotated[list[Scalar], Field(max_length=64)]] = Field(
        default_factory=dict, max_length=32
    )


class ErrorFrame(_Frame):
    type: Literal["error"] = "error"
    code: str
    message: str


InboundFrame = Annotated[
    Hello | Telemetry | SensorUpdate | Ping | Pong | CommandResult, Field(discriminator="type")
]
_INBOUND: TypeAdapter[InboundFrame] = TypeAdapter(InboundFrame)


def parse_inbound(raw: str | bytes, *, max_bytes: int) -> InboundFrame:
    """Validate one frame from a device, or raise ProtocolError with a short code."""
    size = len(raw) if isinstance(raw, bytes) else len(raw.encode("utf-8"))
    if size > max_bytes:
        raise ProtocolError("frame_too_large", f"Frames are limited to {max_bytes} bytes.")
    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ProtocolError("invalid_json", "The frame is not valid JSON.") from error
    if not isinstance(data, dict) or "id" not in data or "v" not in data:
        raise ProtocolError("invalid_frame", "A frame is a JSON object with v, id and type.")
    try:
        return _INBOUND.validate_python(data)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise ProtocolError("invalid_frame", f"{where}: {first['msg']}") from error


def encode(frame: _Frame) -> str:
    return frame.model_dump_json()


# Internal bus events (ZENO_MULTIMODAL_ARCH.md section 2).
#
# These ride the EventBus between the brain's own parts. They are deliberately NOT in
# InboundFrame: a device on the socket can never forge "the owner said X" or "say Y".
# They carry small facts only; image and audio bytes stay in the FrameStore and the
# worker queues.

SourceName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_.:-]{1,64}$")]


class BusEvent(BaseModel):
    """Base for the brain's typed bus events: frozen, strict, wrapped as DeviceEvent."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    KIND: ClassVar[EventKind]
    DEVICE: ClassVar[str] = "brain"

    def to_event(self) -> DeviceEvent:
        return DeviceEvent(
            device=self.DEVICE,
            kind=self.KIND,
            data=self.model_dump(mode="json"),
            received_at=time.time(),
        )

    @classmethod
    def from_event(cls, event: DeviceEvent) -> Self:
        if event.kind != cls.KIND:
            raise ValueError(f"Expected a {cls.KIND} event, got {event.kind}.")
        return cls.model_validate(dict(event.data))


class VisionFrameReceived(BusEvent):
    """An image was stored in the FrameStore; ``frame_id`` fetches it from there."""

    KIND: ClassVar[EventKind] = "vision_frame"

    frame_id: FrameId
    source: SourceName
    mime: Literal["image/jpeg", "image/png"]
    size_bytes: StrictInt = Field(ge=1)
    received_at: float


class AudioCommandReceived(BusEvent):
    """Speech after "Hey Zeno", transcribed. The voice turn handler answers it."""

    KIND: ClassVar[EventKind] = "audio_command"

    utterance_id: FrameId
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    language: Annotated[str, StringConstraints(max_length=16)] = "en"
    confidence: float = Field(ge=0.0, le=1.0)
    duration_s: float = Field(ge=0.0)
    source: SourceName = "microphone"


class SpeechSynthesisRequested(BusEvent):
    """Something the brain wants said out loud, one sentence or short passage."""

    KIND: ClassVar[EventKind] = "speech_request"

    request_id: FrameId = Field(default_factory=lambda: uuid.uuid4().hex)
    text: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    turn_id: FrameId | None = None
    """The voice turn this belongs to, so barge-in can drop the rest of it."""
    interrupt: StrictBool = False
    """Stop whatever is being said and clear the queue before saying this."""
