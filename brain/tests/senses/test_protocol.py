import json

import pytest

from zeno.senses.protocol import (
    Command,
    CommandResult,
    Hello,
    Ping,
    Pong,
    ProtocolError,
    SensorUpdate,
    Telemetry,
    Welcome,
    encode,
    parse_inbound,
)

MAX = 4096


def frame(**fields: object) -> str:
    return json.dumps({"v": 1, "id": "f1", **fields})


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        (frame(type="hello", capabilities=["sensor.temperature", "actuator.relay"]), Hello),
        (frame(type="telemetry", metrics={"cpu_temp": 51.5, "uptime": 120, "ok": True}), Telemetry),
        (frame(type="sensor", sensor="sensor.temperature", value=21.5, unit="C"), SensorUpdate),
        (frame(type="sensor", sensor="sensor.accel", value=[0.1, 0.2, 9.8]), SensorUpdate),
        (frame(type="ping"), Ping),
        (frame(type="pong"), Pong),
        (frame(type="result", command_id="c1", ok=True, detail="done"), CommandResult),
    ],
)
def test_parses_each_inbound_frame_type(raw: str, kind: type) -> None:
    assert isinstance(parse_inbound(raw, max_bytes=MAX), kind)


def test_bytes_input_is_accepted() -> None:
    assert isinstance(parse_inbound(frame(type="ping").encode(), max_bytes=MAX), Ping)


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("not json", "invalid_json"),
        ("[1, 2]", "invalid_frame"),
        (frame(type="teleport"), "invalid_frame"),
        (frame(type="ping", extra="nope"), "invalid_frame"),
        (json.dumps({"v": 2, "id": "f1", "type": "ping"}), "invalid_frame"),
        (json.dumps({"v": 1, "type": "ping"}), "invalid_frame"),
        (frame(type="hello", capabilities=["Bad Name"]), "invalid_frame"),
        (frame(type="sensor", sensor="sensor.temp", value=float("nan")), "invalid_frame"),
        (frame(type="sensor", sensor="sensor.temp", value={"nested": 1}), "invalid_frame"),
        (frame(type="telemetry", metrics={f"m{i}": i for i in range(65)}), "invalid_frame"),
        (frame(type="hello", capabilities=[f"sensor.s{i}" for i in range(33)]), "invalid_frame"),
        (frame(type="command", action="actuator.relay", args={}), "invalid_frame"),
    ],
)
def test_rejects_malformed_frames(raw: str, code: str) -> None:
    with pytest.raises(ProtocolError) as caught:
        parse_inbound(raw, max_bytes=MAX)
    assert caught.value.code == code


def test_rejects_oversized_frames_before_parsing() -> None:
    raw = frame(type="telemetry", metrics={"blob": "x" * 200})
    with pytest.raises(ProtocolError) as caught:
        parse_inbound(raw, max_bytes=100)
    assert caught.value.code == "frame_too_large"


def test_frames_get_an_id_by_default() -> None:
    first, second = Ping(), Ping()
    assert first.id and first.id != second.id


def test_outbound_frames_encode_with_version_type_and_id() -> None:
    command = Command(action="actuator.relay", args={"on": True, "channel": 2})
    data = json.loads(encode(command))
    assert data == {
        "v": 1,
        "id": command.id,
        "type": "command",
        "action": "actuator.relay",
        "args": {"on": True, "channel": 2},
    }
    assert json.loads(encode(Welcome(heartbeat_interval=10.0)))["type"] == "welcome"


def test_frames_are_immutable() -> None:
    ping = Ping()
    with pytest.raises(ValueError):
        ping.id = "changed"  # type: ignore[misc]
