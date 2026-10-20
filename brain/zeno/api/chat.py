"""One chat connection: messages in, the agent's thoughts, actions and answer out."""

import asyncio
import logging
from contextlib import aclosing
from typing import Any

from fastapi import WebSocket

from zeno.agent.events import (
    AgentEvent,
    ApprovalDecided,
    ApprovalRequired,
    Finished,
    Observation,
    StepRejected,
    Thought,
    ToolCall,
)
from zeno.agent.policy import ApprovalRequest
from zeno.api.protocol import ApprovalFrame, CancelFrame, ChatFrame, parse_inbound
from zeno.config import Settings
from zeno.orchestrator import Orchestrator
from zeno.senses.protocol import ProtocolError

log = logging.getLogger(__name__)


class ChatSession:
    """Runs one turn at a time. While a turn waits on an approval, the session keeps
    reading, so the owner's answer (or a cancel) can arrive on the same socket."""

    def __init__(self, websocket: WebSocket, orchestrator: Orchestrator, settings: Settings):
        self.ws = websocket
        self.orchestrator = orchestrator
        self.settings = settings
        self.conversation = orchestrator.new_conversation()
        self.pending: dict[str, ApprovalRequest] = {}
        self._turn: asyncio.Task[None] | None = None
        self._turn_id = ""
        self._send_lock = asyncio.Lock()
        self._closing = False

    async def run(self) -> None:
        await self.ws.accept()
        await self.send(
            {
                "type": "ready",
                "session": self.conversation.id,
                "tools": self.orchestrator.tool_names(),
            }
        )
        try:
            while True:
                message = await self.ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                text = message.get("text")
                if text is None:
                    await self._error("binary_not_supported", "Send JSON text frames.")
                    continue
                try:
                    frame = parse_inbound(
                        text,
                        max_bytes=self.settings.max_frame_bytes,
                        max_chars=self.settings.chat_max_chars,
                        max_context_chars=self.settings.chat_max_context_chars,
                    )
                except ProtocolError as error:
                    await self._error(error.code, error.message)
                    continue
                await self._dispatch(frame)
        finally:
            await self._stop_turn()

    async def _dispatch(self, frame: ChatFrame | ApprovalFrame | CancelFrame) -> None:
        if isinstance(frame, ChatFrame):
            if self._turn is not None and not self._turn.done():
                await self._error("busy", "Zeno is still working on your last message.")
                return
            self._turn_id = frame.id
            self._turn = asyncio.create_task(self._run_turn(frame))
        elif isinstance(frame, ApprovalFrame):
            request = self.pending.get(frame.request_id)
            decided = request is not None and (
                request.approve() if frame.approved else request.deny(frame.reason)
            )
            if not decided:
                await self._error("unknown_request", "There is no pending approval with that id.")
        elif self._turn is not None and not self._turn.done() and frame.id == self._turn_id:
            self._turn.cancel()

    async def _run_turn(self, frame: ChatFrame) -> None:
        turn, step = frame.id, 0

        async def emit(command: dict[str, Any]) -> None:
            await self.send({"type": "command", "turn": turn, "command": command})

        try:
            events = self.orchestrator.respond(
                self.conversation, frame.text, emit=emit, context=frame.context
            )
            async with aclosing(events) as stream:
                async for event in stream:
                    step = getattr(event, "step", step)
                    for out in self._frames(turn, event):
                        await self.send(out)
        except asyncio.CancelledError:
            # Cancelled by the owner (a cancel frame) or because the socket closed.
            self.pending.clear()
            if self._closing:
                raise
            await self.send({"type": "done", "turn": turn, "outcome": "cancelled", "steps": step})
        except Exception:
            log.exception("Chat turn %s failed", turn)
            await self._error("internal_error", "Something went wrong while answering.")
            await self.send({"type": "done", "turn": turn, "outcome": "error", "steps": step})

    def _frames(self, turn: str, event: AgentEvent) -> list[dict[str, Any]]:
        if isinstance(event, Thought):
            return [{"type": "thought", "turn": turn, "step": event.step, "text": event.text}]
        if isinstance(event, ToolCall):
            return [
                {
                    "type": "tool_call",
                    "turn": turn,
                    "step": event.step,
                    "tool": event.tool,
                    "args": dict(event.args),
                    "risk": event.risk.value,
                }
            ]
        if isinstance(event, ApprovalRequired):
            request = event.request
            self.pending[request.id] = request
            return [
                {
                    "type": "approval_required",
                    "turn": turn,
                    "step": event.step,
                    "request_id": request.id,
                    "tool": request.tool,
                    "args": dict(request.args),
                    "risk": request.risk.value,
                    "thought": request.thought,
                    "description": request.description,
                    "timeout": self.settings.agent_approval_timeout,
                }
            ]
        if isinstance(event, ApprovalDecided):
            self.pending.pop(event.request_id, None)
            return [
                {
                    "type": "approval",
                    "turn": turn,
                    "step": event.step,
                    "request_id": event.request_id,
                    "approved": event.approved,
                    "by": event.by,
                    "reason": event.reason,
                }
            ]
        if isinstance(event, Observation):
            return [
                {
                    "type": "observation",
                    "turn": turn,
                    "step": event.step,
                    "tool": event.tool,
                    "ok": event.ok,
                    "content": event.content,
                }
            ]
        if isinstance(event, StepRejected):
            return [
                {"type": "step_rejected", "turn": turn, "step": event.step, "error": event.error}
            ]
        if isinstance(event, Finished):
            return [
                {"type": "text", "turn": turn, "text": event.answer},
                {"type": "done", "turn": turn, "outcome": event.outcome, "steps": event.steps},
            ]
        return []

    async def send(self, frame: dict[str, Any]) -> None:
        async with self._send_lock:  # turn and reader tasks both write
            await self.ws.send_json(frame)

    async def _error(self, code: str, message: str) -> None:
        await self.send({"type": "error", "code": code, "message": message})

    async def _stop_turn(self) -> None:
        self._closing = True
        turn = self._turn
        if turn is None:
            return
        turn.cancel()
        # asyncio.wait, not await turn: never re-raise the turn's CancelledError as
        # if this session itself had been cancelled.
        await asyncio.wait({turn})
        if not turn.cancelled() and turn.exception() is not None:
            log.warning("Chat turn ended with an error", exc_info=turn.exception())
