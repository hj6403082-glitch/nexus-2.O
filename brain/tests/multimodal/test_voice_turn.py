"""VoiceTurnHandler: a spoken command runs one ReAct turn off the bus dispatcher, and the
answer is pushed to speech. Voice approvals are off."""

import asyncio
import json
from collections.abc import AsyncGenerator, Callable, Sequence
from typing import Any

import pytest

from tests.multimodal.conftest import Recorder, eventually
from zeno.agent.audit import MemoryAuditLog
from zeno.agent.tools.base import Risk, ToolArgs, tool
from zeno.config import Settings
from zeno.inference.base import ChatMessage, GenerationParams
from zeno.inference.fake import ScriptedEngine
from zeno.memory.episodic import EpisodicMemory
from zeno.memory.fake import HashEmbedder, InMemoryVectorStore
from zeno.memory.manager import MemoryManager
from zeno.memory.semantic import FactMemory
from zeno.multimodal.voice_turn import VOICE_APPROVAL_REFUSAL, VoiceTurnHandler
from zeno.orchestrator import Orchestrator
from zeno.senses.events import DeviceEvent, EventBus, EventKind
from zeno.senses.protocol import AudioCommandReceived, SpeechSynthesisRequested


class NoArgs(ToolArgs):
    pass


calls: list[str] = []


@tool(risk=Risk.MUTATING, timeout=1.0)
async def unlock_door(args: NoArgs) -> str:
    """Unlock the front door."""
    calls.append("unlock_door")
    return "unlocked"


@tool(risk=Risk.PRIVILEGED, timeout=1.0)
async def root_shell(args: NoArgs) -> str:
    """Run a privileged command."""
    calls.append("root_shell")
    return "done"


def act(name: str) -> str:
    return json.dumps({"thought": "Use the tool.", "action": {"tool": name, "args": {}}})


def final(answer: str) -> str:
    return json.dumps({"thought": "Answer.", "final": answer})


class GatedEngine(ScriptedEngine):
    """Waits for ``gate`` before answering, so a turn can be held mid-flight."""

    def __init__(self, responses: Sequence[str]) -> None:
        super().__init__(responses)
        self.gate = asyncio.Event()

    async def stream(
        self, messages: Sequence[ChatMessage], params: GenerationParams | None = None
    ) -> AsyncGenerator[str, None]:
        await self.gate.wait()
        async for chunk in super().stream(messages, params):
            yield chunk


def orchestrator(engine: ScriptedEngine, bus: EventBus, **settings: Any) -> Orchestrator:
    store, embedder = InMemoryVectorStore(), HashEmbedder()
    return Orchestrator(
        engine=engine,
        memory=MemoryManager(
            facts=FactMemory(store, embedder), episodes=EpisodicMemory(store, embedder)
        ),
        audit=MemoryAuditLog(),
        settings=Settings(_env_file=None, **settings),
        base_tools=[unlock_door, root_shell],
        speak=bus.publish,
    )


def heard(bus: EventBus, text: str, uid: str = "u1") -> None:
    bus.publish(
        AudioCommandReceived(utterance_id=uid, text=text, confidence=0.9, duration_s=1.0).to_event()
    )


def spoken(recorder: Recorder) -> list[str]:
    return [SpeechSynthesisRequested.from_event(e).text for e in recorder.events]


@pytest.fixture(autouse=True)
def _reset_calls() -> None:
    calls.clear()


async def test_a_spoken_command_is_answered_out_loud(
    bus: EventBus, record: Callable[[EventKind], Recorder]
) -> None:
    speech = record("speech_request")
    engine = ScriptedEngine([final("It is nine. Have a good night.")])
    handler = VoiceTurnHandler(orchestrator(engine, bus), bus)
    handler.attach()
    heard(bus, "Test command")
    await eventually(lambda: len(speech.events) == 2)
    assert spoken(speech) == ["It is nine.", "Have a good night."]
    prompt = engine.calls[0][0]
    assert "Test command" in prompt[-1].content
    assert "spoken aloud" in prompt[-1].content
    assert all(SpeechSynthesisRequested.from_event(e).turn_id == "u1" for e in speech.events)


async def test_the_bus_keeps_flowing_while_a_turn_runs(
    bus: EventBus, record: Callable[[EventKind], Recorder]
) -> None:
    engine = GatedEngine([final("Done.")])
    handler = VoiceTurnHandler(orchestrator(engine, bus), bus)
    handler.attach()
    sensors = record("sensor")
    heard(bus, "Think hard")
    await eventually(lambda: handler.busy)
    bus.publish(DeviceEvent(device="pi", kind="sensor", data={"t": 21}, received_at=0))
    await eventually(lambda: bool(sensors.events))  # delivered while the turn is held
    engine.gate.set()
    await eventually(lambda: not handler.busy)


async def test_voice_approvals_are_refused_and_explained(
    bus: EventBus, record: Callable[[EventKind], Recorder]
) -> None:
    speech = record("speech_request")
    engine = ScriptedEngine([act("unlock_door"), final("Unlocked.")])
    handler = VoiceTurnHandler(orchestrator(engine, bus), bus)
    handler.attach()
    heard(bus, "Unlock the door")
    await eventually(lambda: bool(speech.events))
    await eventually(lambda: not handler.busy)
    assert calls == []
    await bus.drain()
    assert " ".join(spoken(speech)) == VOICE_APPROVAL_REFUSAL
    assert handler.refused == 1


async def test_privileged_tools_are_not_offered_to_voice_turns(bus: EventBus) -> None:
    engine = ScriptedEngine([final("Okay.")])
    handler = VoiceTurnHandler(orchestrator(engine, bus), bus)
    handler.attach()
    heard(bus, "Hello")
    await eventually(lambda: bool(engine.calls))
    system = engine.calls[0][0][0].content
    assert "unlock_door" in system
    assert "root_shell" not in system


async def test_a_new_command_cancels_the_running_turn(
    bus: EventBus, record: Callable[[EventKind], Recorder]
) -> None:
    speech = record("speech_request")
    engine = GatedEngine([final("Old answer."), final("New answer.")])
    handler = VoiceTurnHandler(orchestrator(engine, bus), bus)
    handler.attach()
    heard(bus, "First", uid="u1")
    await eventually(lambda: handler.busy)
    heard(bus, "Second", uid="u2")
    await eventually(lambda: handler.cancelled == 1)
    engine.gate.set()
    await eventually(lambda: bool(speech.events))
    await eventually(lambda: not handler.busy)
    assert spoken(speech) == ["Old answer."] or spoken(speech) == ["New answer."]
    assert all(SpeechSynthesisRequested.from_event(e).turn_id == "u2" for e in speech.events)


async def test_cancel_and_detach(bus: EventBus) -> None:
    engine = GatedEngine([final("Never.")])
    handler = VoiceTurnHandler(orchestrator(engine, bus), bus)
    detach = handler.attach()
    heard(bus, "Hold on")
    await eventually(lambda: handler.busy)
    await handler.stop()
    assert not handler.busy
    detach()
    heard(bus, "Ignored")
    await bus.drain()
    assert not handler.busy


async def test_voice_turns_remember_the_conversation(bus: EventBus) -> None:
    engine = ScriptedEngine([final("Hi Boss."), final("You said hello.")])
    handler = VoiceTurnHandler(orchestrator(engine, bus), bus)
    handler.attach()
    heard(bus, "Hello", uid="u1")
    await eventually(lambda: len(engine.calls) == 1 and not handler.busy)
    heard(bus, "What did I say?", uid="u2")
    await eventually(lambda: len(engine.calls) == 2)
    contents = [m.content for m in engine.calls[1][0]]
    assert any("Hello" in c for c in contents)
    assert "Hi Boss." in contents


async def test_chat_turns_are_silent_unless_configured(
    bus: EventBus, record: Callable[[EventKind], Recorder]
) -> None:
    speech = record("speech_request")

    async def nowhere(command: dict[str, Any]) -> None:
        return None

    quiet = orchestrator(ScriptedEngine([final("Typed answer.")]), bus)
    _ = [e async for e in quiet.respond(quiet.new_conversation(), "hi", emit=nowhere)]
    await bus.drain()
    assert speech.events == []

    loud = orchestrator(ScriptedEngine([final("Typed answer.")]), bus, speak_chat_answers=True)
    _ = [e async for e in loud.respond(loud.new_conversation(), "hi", emit=nowhere)]
    await eventually(lambda: spoken(speech) == ["Typed answer."])
