"""What a ReAct run emits, in order, to whoever drives it (API, voice, tests)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from zeno.agent.policy import ApprovalRequest
from zeno.agent.tools.base import Risk

Outcome = Literal["answered", "step_limit", "loop_detected", "error", "cancelled"]


@dataclass(frozen=True, slots=True)
class Thought:
    step: int
    text: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    step: int
    tool: str
    args: Mapping[str, Any]
    risk: Risk


@dataclass(frozen=True, slots=True)
class ApprovalRequired:
    """The run is paused: call ``request.approve()`` or ``request.deny()``."""

    step: int
    request: ApprovalRequest


@dataclass(frozen=True, slots=True)
class ApprovalDecided:
    step: int
    request_id: str
    approved: bool
    by: str
    """Who decided: the approver's name, or "timeout" when nobody answered in time."""
    reason: str


@dataclass(frozen=True, slots=True)
class Observation:
    step: int
    tool: str
    ok: bool
    content: str


@dataclass(frozen=True, slots=True)
class StepRejected:
    """The model's output was not a valid step; it is told so and tries again."""

    step: int
    error: str


@dataclass(frozen=True, slots=True)
class Finished:
    outcome: Outcome
    answer: str
    steps: int


AgentEvent = (
    Thought | ToolCall | ApprovalRequired | ApprovalDecided | Observation | StepRejected | Finished
)
