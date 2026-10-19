"""Frames on the chat socket. Inbound frames are validated; outbound are plain dicts.

Outbound ``text``, ``command``, ``error`` and ``done`` frames match the web app's
``StreamEvent`` shapes, so its decoder can read them as they are.
"""

import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)

from zeno.senses.protocol import ProtocolError

TurnId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")]


class _Inbound(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChatFrame(_Inbound):
    type: Literal["chat"]
    id: TurnId
    text: str = Field(min_length=1)


class ApprovalFrame(_Inbound):
    type: Literal["approval"]
    request_id: Annotated[str, StringConstraints(max_length=64)]
    approved: StrictBool
    reason: Annotated[str, StringConstraints(max_length=500)] = ""


class CancelFrame(_Inbound):
    type: Literal["cancel"]
    id: TurnId


Inbound = Annotated[ChatFrame | ApprovalFrame | CancelFrame, Field(discriminator="type")]
_INBOUND: TypeAdapter[ChatFrame | ApprovalFrame | CancelFrame] = TypeAdapter(Inbound)


def parse_inbound(
    raw: str, *, max_bytes: int, max_chars: int
) -> ChatFrame | ApprovalFrame | CancelFrame:
    if len(raw.encode("utf-8")) > max_bytes:
        raise ProtocolError("frame_too_large", f"Frames are limited to {max_bytes} bytes.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ProtocolError("invalid_json", "Frames must be JSON objects.") from None
    try:
        frame = _INBOUND.validate_python(data)
    except ValidationError as error:
        raise ProtocolError("invalid_frame", _first_problem(error)) from None
    if isinstance(frame, ChatFrame) and len(frame.text) > max_chars:
        raise ProtocolError("invalid_frame", f"Messages are limited to {max_chars} characters.")
    return frame


def _first_problem(error: ValidationError) -> str:
    problem = error.errors()[0]
    where = ".".join(str(part) for part in problem["loc"]) or "frame"
    return f"{where}: {problem['msg']}"
