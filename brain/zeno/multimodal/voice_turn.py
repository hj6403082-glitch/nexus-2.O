"""VoiceTurnHandler: answers spoken commands with a normal ReAct turn, out loud.

The bus dispatcher awaits handlers one at a time, so the handler only starts a task
and returns; a whole ReAct run inside it would freeze the bus. One voice turn runs at
a time: a new command (or a barge-in) cancels the one in flight.

Approvals by voice are off: anyone in the room, or a TV, can say "yes". A voice turn
that reaches a step needing approval is denied at once and Zeno says why.
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import aclosing
from typing import Any

from zeno.agent.events import ApprovalRequired
from zeno.multimodal.speech import say
from zeno.multimodal.workers import cancel_task
from zeno.orchestrator import Orchestrator
from zeno.senses.events import DeviceEvent, EventBus
from zeno.senses.protocol import AudioCommandReceived

log = logging.getLogger(__name__)

SPOKEN_CONTEXT = "spoken aloud via the microphone; answer briefly, for listening"
VOICE_APPROVAL_REFUSAL = "I can't do that by voice yet. Ask me in the chat and approve it there."
VOICE_APPROVAL_REASON = "voice approvals are off"


class VoiceTurnHandler:
    def __init__(self, orchestrator: Orchestrator, bus: EventBus) -> None:
        self._orchestrator = orchestrator
        self._bus = bus
        self._conversation = orchestrator.new_conversation()
        self._task: asyncio.Task[None] | None = None
        self.cancelled = 0
        self.refused = 0

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def attach(self) -> Callable[[], None]:
        return self._bus.subscribe(self._on_command, kind="audio_command")

    def cancel(self) -> None:
        """Abandon the turn in flight, if any (barge-in)."""
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            self.cancelled += 1

    async def stop(self) -> None:
        task, self._task = self._task, None
        await cancel_task(task)

    async def _on_command(self, event: DeviceEvent) -> None:
        command = AudioCommandReceived.from_event(event)
        self.cancel()
        self._task = asyncio.create_task(self._turn(command), name="zeno-voice-turn")

    async def _turn(self, command: AudioCommandReceived) -> None:
        async def nowhere(_: dict[str, Any]) -> None:
            return None  # no screen to send UI commands to

        turn_id = command.utterance_id
        events = self._orchestrator.respond(
            self._conversation,
            command.text,
            emit=nowhere,
            context=SPOKEN_CONTEXT,
            origin="voice",
            speak=True,
            turn_id=turn_id,
        )
        try:
            async with aclosing(events) as stream:
                async for item in stream:
                    if isinstance(item, ApprovalRequired):
                        item.request.deny(VOICE_APPROVAL_REASON, by="voice-policy")
                        self.refused += 1
                        say(self._bus.publish, VOICE_APPROVAL_REFUSAL, turn_id=turn_id)
                        return  # end the run here rather than speak a second answer
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Voice turn failed")
            say(self._bus.publish, "Sorry, something went wrong.", turn_id=turn_id)
