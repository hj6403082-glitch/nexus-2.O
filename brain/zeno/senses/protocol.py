"""The device wire protocol: versioned JSON frames, validated strictly at the edge.

Every frame is ``{"v": 1, "id": ..., "type": ..., ...}``. Devices may only send the
inbound types; commands only ever flow from the brain to a device.
"""

import json
import uuid
from enum import IntEnum
from typing import Annotated, Any, Literal

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
