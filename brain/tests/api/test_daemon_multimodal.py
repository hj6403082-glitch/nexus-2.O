"""The daemon wires the multimodal layer: switches, factories, start and unwind, and one
end-to-end voice round trip (mic chunks -> STT -> ReAct -> TTS -> speaker) on fakes."""

import json
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.api.conftest import brain_settings, wait_until
from tests.multimodal.conftest import png
from zeno.agent.tools.vision import VisionArgs
from zeno.config import Settings
from zeno.daemon import ZenoDaemon
from zeno.inference.fake import ScriptedEngine
from zeno.memory.fake import HashEmbedder, InMemoryVectorStore
from zeno.multimodal.adapters import MultimodalFactories, default_factories
from zeno.multimodal.fake import FakeAudioSink, FakeSttEngine, FakeTtsEngine, FakeVisionEngine
from zeno.multimodal.queues import AudioChunk

FRAME = b"\x01\x00" * 1280


class Fakes:
    def __init__(self) -> None:
        self.vision = FakeVisionEngine()
        self.stt = FakeSttEngine()
        self.tts = FakeTtsEngine()
        self.sink = FakeAudioSink()

    def factories(self, *, voice_missing: str | None = None) -> MultimodalFactories:
        return MultimodalFactories(
            vision=lambda _: self.vision,
            stt=lambda _: self.stt,
            tts=lambda _: self.tts,
            sink=lambda _: self.sink,
            voice_missing=lambda _: voice_missing,
        )


def daemon(
    tmp_path: Path, factories: MultimodalFactories | None, responses: list[str], **overrides: Any
) -> ZenoDaemon:
    engine = ScriptedEngine(responses)
    return ZenoDaemon(
        brain_settings(tmp_path, **overrides),
        engine_factory=lambda _: engine,
        embedder_factory=lambda _: HashEmbedder(),
        store_factory=lambda _: InMemoryVectorStore(),
        multimodal=factories,
    )


def final(answer: str) -> str:
    return json.dumps({"thought": "Answer.", "final": answer})


def test_vision_is_off_by_default(tmp_path: Path) -> None:
    d = daemon(tmp_path, Fakes().factories(), [])
    with TestClient(d.app):
        assert d.vision is None
        assert "analyze_vision_frame" not in d.services.base_tools


def test_vision_tool_works_through_the_daemon(tmp_path: Path) -> None:
    fakes = Fakes()
    d = daemon(tmp_path, fakes.factories(), [], vision=True)
    with TestClient(d.app) as client:
        assert d.vision is not None and d.frames is not None
        d.frames.put(png(), source="upload")
        tool = d.services.base_tools["analyze_vision_frame"]
        result = client.portal.call(tool.invoke, VisionArgs(question="What is it?"))  # type: ignore[union-attr]
        assert "I see a test image" in result
    assert d.vision is None
    wait_until(lambda: fakes.vision.closed)


def test_voice_round_trip_on_fakes(tmp_path: Path) -> None:
    fakes = Fakes()
    d = daemon(tmp_path, fakes.factories(), [final("It is nine. Good night.")], voice=True)
    with TestClient(d.app) as client:
        assert d.voice is not None and d.queues is not None
        queues = d.queues

        def speak_into_the_mic() -> None:
            for seq in range(4):
                last = seq == 3
                queues.offer_audio(
                    AudioChunk("u1", seq, FRAME, final=last, end_reason="silence" if last else None)
                )

        client.portal.call(_on_loop, speak_into_the_mic)  # type: ignore[union-attr]
        wait_until(lambda: len(fakes.sink.played) == 2)
        assert fakes.tts.calls == ["It is nine.", "Good night."]
    assert d.voice is None


async def _on_loop(func: Any) -> None:
    func()


def test_voice_stays_off_when_its_engines_are_missing(tmp_path: Path) -> None:
    d = daemon(tmp_path, Fakes().factories(voice_missing="faster-whisper"), [], voice=True)
    with TestClient(d.app):
        assert d.voice is None


def test_voice_can_be_turned_off(tmp_path: Path) -> None:
    d = daemon(tmp_path, Fakes().factories(), [], voice=False)
    with TestClient(d.app):
        assert d.voice is None


def test_default_factories_report_what_is_missing() -> None:
    settings = Settings(_env_file=None)
    missing = default_factories().voice_missing(settings)
    # In the default test environment faster-whisper is a placeholder, not installed.
    assert missing is None or "faster-whisper" in missing or "voice" in missing


def test_the_listener_gets_the_capture_sink_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[Any] = []

    class FakeListener:
        def start(self, loop: Any = None) -> None:
            pass

        def stop(self) -> None:
            pass

    def build(settings: Any, bus: Any, **kw: Any) -> FakeListener:
        built.append(kw.get("capture_sink"))
        return FakeListener()

    monkeypatch.setattr("zeno.daemon.sys.platform", "win32")
    monkeypatch.setattr("zeno.senses.audio_listener.build_listener", build)
    d = daemon(tmp_path, Fakes().factories(), [], voice=True, wakeword=True)
    with TestClient(d.app):
        assert d.queues is not None
        assert built == [d.queues.offer_audio]


def test_no_capture_sink_without_voice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[Any] = []

    class FakeListener:
        def start(self, loop: Any = None) -> None:
            pass

        def stop(self) -> None:
            pass

    def build(settings: Any, bus: Any, **kw: Any) -> FakeListener:
        built.append(kw.get("capture_sink"))
        return FakeListener()

    monkeypatch.setattr("zeno.daemon.sys.platform", "win32")
    monkeypatch.setattr("zeno.senses.audio_listener.build_listener", build)
    d = daemon(tmp_path, Fakes().factories(), [], voice=False, wakeword=True)
    with TestClient(d.app):
        assert built == [None]
