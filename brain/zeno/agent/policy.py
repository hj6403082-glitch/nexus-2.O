"""Human-in-the-loop approval for state-changing tools."""

import asyncio
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from zeno.agent.tools.base import Risk


def needs_approval(risk: Risk) -> bool:
    """READ_ONLY tools run on their own; anything else waits for the owner."""
    return risk is not Risk.READ_ONLY


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    approved: bool
    by: str
    reason: str = ""


@dataclass(eq=False)
class ApprovalRequest:
    """One pending decision. The agent waits until ``approve`` or ``deny`` is called
    (or its approval timeout passes, which counts as a denial)."""

    tool: str
    args: Mapping[str, Any]
    risk: Risk
    thought: str
    description: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    _future: asyncio.Future[ApprovalDecision] = field(
        default_factory=lambda: asyncio.get_running_loop().create_future(), repr=False
    )

    @property
    def decided(self) -> bool:
        return self._future.done()

    def approve(self, *, by: str = "owner") -> bool:
        """Allow this one call. Returns False if it was already decided."""
        return self._decide(ApprovalDecision(True, by))

    def deny(self, reason: str = "", *, by: str = "owner") -> bool:
        """Refuse this call. Returns False if it was already decided."""
        return self._decide(ApprovalDecision(False, by, reason))

    def _decide(self, decision: ApprovalDecision) -> bool:
        if self._future.done():
            return False
        self._future.set_result(decision)
        return True

    async def wait(self, timeout: float) -> ApprovalDecision:  # noqa: ASYNC109  # expiry is a denial, not an error
        try:
            return await asyncio.wait_for(asyncio.shield(self._future), timeout)
        except TimeoutError:
            self._decide(ApprovalDecision(False, "timeout", "No answer in time."))
            return self._future.result()
