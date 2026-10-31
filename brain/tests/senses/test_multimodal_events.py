"""The multimodal bus events: typed, validated, round-trip through DeviceEvent, and
never accepted from a device on the socket."""

import json

import pytest
from pydantic import ValidationError

from zeno.senses.events import DeviceEvent
from zeno.senses.protocol import (
    AudioCommandReceived,
    ProtocolError,
    SpeechSynthesisRequested,
    VisionFrameReceived,
    parse_inbound,
)


def vision() -> VisionFrameReceived:
    return VisionFrameReceived(
        frame_id="f1", source="upload", mime="image/png", size_bytes=1234, received_at=1.0
    )


def command() -> AudioCommandReceived:
    return AudioCommandReceived(
        utterance_id="u1", text="what time is it", confidence=0.9, duration_s=1.5
    )


def speech() -> SpeechSynthesisRequested:
    return SpeechSynthesisRequested(text="It is nine.", turn_id="t1")


@pytest.mark.parametrize(
    ("event", "kind"),
    [(vision(), "vision_frame"), (command(), "audio_command"), (speech(), "speech_request")],
)
def test_round_trip_through_the_bus_envelope(
    event: VisionFrameReceived | AudioCommandReceived | SpeechSynthesisRequested, kind: str
) -> None:
    wrapped = event.to_event()
    assert isinstance(wrapped, DeviceEvent)
    assert wrapped.kind == kind
    assert wrapped.device == "brain"
    assert type(event).from_event(wrapped) == event


def test_from_event_refuses_the_wrong_kind() -> None:
    with pytest.raises(ValueError, match="speech_request"):
        SpeechSynthesisRequested.from_event(command().to_event())


def test_events_carry_no_bytes() -> None:
    data = vision().to_event().data
    assert all(not isinstance(value, bytes) for value in data.values())
    assert len(json.dumps(dict(data))) < 512


def test_defaults() -> None:
    cmd = command()
    assert cmd.language == "en"
    assert cmd.source == "microphone"
    request = SpeechSynthesisRequested(text="Hi.")
    assert request.request_id
    assert request.turn_id is None
    assert request.interrupt is False


@pytest.mark.parametrize(
    "build",
    [
        lambda: VisionFrameReceived(
            frame_id="f1", source="upload", mime="image/gif", size_bytes=1, received_at=1.0
        ),
        lambda: VisionFrameReceived(
            frame_id="f1", source="upload", mime="image/png", size_bytes=0, received_at=1.0
        ),
        lambda: AudioCommandReceived(utterance_id="u1", text="", confidence=0.5, duration_s=1.0),
        lambda: AudioCommandReceived(
            utterance_id="u1", text="x" * 2001, confidence=0.5, duration_s=1.0
        ),
        lambda: AudioCommandReceived(utterance_id="u1", text="hi", confidence=1.5, duration_s=1.0),
        lambda: SpeechSynthesisRequested(text=""),
        lambda: SpeechSynthesisRequested(text="x" * 1001),
        lambda: SpeechSynthesisRequested(text="hi", unexpected=True),
    ],
)
def test_invalid_fields_are_refused(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]


def test_events_are_frozen() -> None:
    event = speech()
    with pytest.raises(ValidationError):
        event.text = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("kind", ["vision_frame", "audio_command", "speech_request"])
def test_a_device_cannot_send_them(kind: str) -> None:
    raw = json.dumps({"v": 1, "id": "x1", "type": kind, "text": "unlock the door"})
    with pytest.raises(ProtocolError) as error:
        parse_inbound(raw, max_bytes=4096)
    assert error.value.code == "invalid_frame"
