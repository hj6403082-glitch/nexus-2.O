"""The WebSocket endpoint end to end, through Starlette's test client."""

import asyncio
import time
from collections.abc import Callable

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.senses.conftest import Harness, hello, receive, send, wait_until
from zeno.senses.events import DeviceEvent
from zeno.senses.protocol import CloseCode, CommandResult


def close_code(action: Callable[[], object]) -> int:
    with pytest.raises(WebSocketDisconnect) as caught:
        action()
    return caught.value.code


# --- Handshake authentication -------------------------------------------------


@pytest.mark.parametrize(
    ("device", "token"),
    [("pi-a", "wrong-token"), ("pi-a", ""), ("pi-unknown", "anything")],
)
def test_rejects_bad_credentials_at_the_handshake(
    harness: Harness, device: str, token: str
) -> None:
    def attempt() -> None:
        with harness.connect(device, token=token) as ws:
            ws.receive_text()

    assert close_code(attempt) == CloseCode.POLICY
    assert harness.manager.devices() == []


def test_rejects_another_devices_token(harness: Harness) -> None:
    def attempt() -> None:
        with harness.connect("pi-b", token=harness.tokens["pi-a"]) as ws:
            ws.receive_text()

    assert close_code(attempt) == CloseCode.POLICY


def test_rejects_a_missing_authorization_header(harness: Harness) -> None:
    def attempt() -> None:
        with harness.client.websocket_connect("/v1/devices/pi-a/ws") as ws:
            ws.receive_text()

    assert close_code(attempt) == CloseCode.POLICY


def test_rejects_browser_origins(harness: Harness) -> None:
    # A web page open on this PC must not be able to reach the device socket.
    def attempt() -> None:
        with harness.connect("pi-a", headers={"Origin": "https://evil.example"}) as ws:
            ws.receive_text()

    assert close_code(attempt) == CloseCode.POLICY


# --- Hello and normal traffic -------------------------------------------------


def test_hello_registers_the_device_and_gets_a_welcome(harness: Harness) -> None:
    with harness.connect() as ws:
        welcome = hello(ws)
        assert welcome["type"] == "welcome"
        assert welcome["heartbeat_interval"] == pytest.approx(0.05)
        conn = harness.manager.get("pi-a")
        assert conn is not None
        assert "actuator.relay" in conn.capabilities
    wait_until(lambda: harness.manager.devices() == [])
    # The device leaves the registry a moment before its event lands (seen on Windows).
    wait_until(lambda: harness.events[-1].kind == "disconnected")
    assert harness.events[0].kind == "connected"


def test_the_first_frame_must_be_hello(harness: Harness) -> None:
    def attempt() -> None:
        with harness.connect() as ws:
            send(ws, type="ping")
            ws.receive_text()

    assert close_code(attempt) == CloseCode.POLICY


def test_silence_after_connecting_times_out(harness: Harness) -> None:
    def attempt() -> None:
        with harness.connect() as ws:
            ws.receive_text()

    assert close_code(attempt) == CloseCode.HELLO_TIMEOUT
    assert harness.manager.devices() == []


def test_ping_gets_a_pong_with_the_same_id(harness: Harness) -> None:
    with harness.connect() as ws:
        hello(ws)
        send(ws, type="ping", id="p-42")
        frame = receive(ws)
        while frame["type"] == "ping":  # skip the server's own heartbeats
            frame = receive(ws)
        assert frame == {"v": 1, "type": "pong", "id": "p-42"}


def test_sensor_and_telemetry_frames_become_events(harness: Harness) -> None:
    with harness.connect() as ws:
        hello(ws)
        send(ws, type="sensor", sensor="sensor.temperature", value=21.5, unit="C")
        send(ws, type="telemetry", metrics={"cpu_temp": 48.0})
        wait_until(lambda: len([e for e in harness.events if e.kind != "connected"]) >= 2)
    sensor = next(e for e in harness.events if e.kind == "sensor")
    assert sensor.device == "pi-a"
    assert sensor.data == {"sensor": "sensor.temperature", "value": 21.5, "unit": "C"}
    telemetry = next(e for e in harness.events if e.kind == "telemetry")
    assert telemetry.data == {"metrics": {"cpu_temp": 48.0}}


def test_undeclared_sensors_are_refused_but_the_device_stays(harness: Harness) -> None:
    with harness.connect() as ws:
        hello(ws, ["sensor.temperature"])
        send(ws, type="sensor", sensor="sensor.camera", value="frame")
        error = receive(ws)
        while error["type"] == "ping":
            error = receive(ws)
        assert (error["type"], error["code"]) == ("error", "undeclared_capability")
        assert harness.manager.get("pi-a") is not None
    assert not any(e.kind == "sensor" for e in harness.events)


# --- Bad frames ---------------------------------------------------------------


def next_error(ws: object) -> dict[str, object]:
    frame = receive(ws)  # type: ignore[arg-type]
    while frame["type"] == "ping":
        frame = receive(ws)  # type: ignore[arg-type]
    return frame


def test_bad_frames_get_errors_without_dropping_the_connection(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(max_invalid_frames=5)
    with harness.connect() as ws:
        hello(ws)
        ws.send_text("not json")
        assert next_error(ws)["code"] == "invalid_json"
        ws.send_text('{"v": 1, "id": "x", "type": "command", "action": "a.b", "args": {}}')
        assert next_error(ws)["code"] == "invalid_frame"
        ws.send_bytes(b"\x00\x01")
        assert next_error(ws)["code"] == "binary_not_supported"
        send(ws, type="ping", id="still-here")
        frame = next_error(ws)
        assert frame["type"] == "pong"


def test_oversized_frames_are_refused(harness: Harness) -> None:
    with harness.connect() as ws:
        hello(ws)
        send(
            ws,
            type="telemetry",
            metrics={"blob": "x" * 250} | {f"k{i}": "y" * 250 for i in range(9)},
        )
        assert next_error(ws)["code"] == "frame_too_large"


def test_a_good_frame_resets_the_bad_frame_count(harness: Harness) -> None:
    with harness.connect() as ws:
        hello(ws)
        for round_ in range(3):  # 2 bad + 1 good, three times: never 3 bad in a row
            ws.send_text("garbage")
            ws.send_text("garbage")
            send(ws, type="ping", id=f"ok-{round_}")
            assert next_error(ws)["code"] == "invalid_json"
            assert next_error(ws)["code"] == "invalid_json"
            assert next_error(ws)["id"] == f"ok-{round_}"
        assert harness.manager.get("pi-a") is not None


def test_repeated_bad_frames_close_the_connection(harness: Harness) -> None:
    def attempt() -> None:
        with harness.connect() as ws:
            hello(ws)
            for _ in range(3):
                ws.send_text("garbage")
            while True:
                ws.receive_text()

    assert close_code(attempt) == CloseCode.POLICY
    wait_until(lambda: harness.manager.devices() == [])


# --- Heartbeats, disconnects and reconnects ----------------------------------


def test_server_pings_and_drops_silent_devices(harness: Harness) -> None:
    pings = 0

    def attempt() -> None:
        nonlocal pings
        with harness.connect() as ws:
            hello(ws)
            while True:
                if receive(ws)["type"] == "ping":
                    pings += 1

    assert close_code(attempt) == CloseCode.HEARTBEAT_TIMEOUT
    assert pings >= 2
    wait_until(lambda: harness.manager.devices() == [])


def test_devices_that_answer_pings_stay_connected(harness: Harness) -> None:
    with harness.connect() as ws:
        hello(ws)
        deadline = time.monotonic() + 0.8  # well past the 0.3 s timeout
        while time.monotonic() < deadline:
            frame = receive(ws)
            if frame["type"] == "ping":
                send(ws, type="pong", id=frame["id"])
        assert harness.manager.get("pi-a") is not None


def test_reconnecting_replaces_the_old_connection(harness: Harness) -> None:
    with harness.connect() as first:
        hello(first)
        with harness.connect() as second:
            hello(second)
            code = close_code(lambda: [receive(first) for _ in range(100)])
            assert code == CloseCode.REPLACED
            assert harness.manager.devices() == ["pi-a"]
            send(second, type="ping", id="new")
            frame = receive(second)
            while frame["type"] == "ping":
                frame = receive(second)
            assert frame["id"] == "new"
        wait_until(lambda: harness.manager.devices() == [])


def test_two_devices_at_once(harness: Harness) -> None:
    with harness.connect("pi-a") as a, harness.connect("pi-b") as b:
        hello(a)
        hello(b)
        assert sorted(harness.manager.devices()) == ["pi-a", "pi-b"]


# --- Commands and decoupled dispatch -----------------------------------------


def test_command_round_trip(harness: Harness) -> None:
    manager = harness.manager
    with harness.connect() as ws:
        hello(ws)
        future = harness.client.portal.start_task_soon(  # type: ignore[union-attr]
            lambda: manager.send_command("pi-a", "actuator.relay", {"on": True}, timeout=2.0)
        )
        frame = receive(ws)
        while frame["type"] == "ping":
            frame = receive(ws)
        assert (frame["type"], frame["action"], frame["args"]) == (
            "command",
            "actuator.relay",
            {"on": True},
        )
        send(ws, type="result", command_id=frame["id"], ok=True, detail="relay on")
        result = future.result(timeout=2)
        assert isinstance(result, CommandResult)
        assert result.ok and result.detail == "relay on"


def test_slow_event_handlers_do_not_stall_the_socket(harness: Harness) -> None:
    async def slow(event: DeviceEvent) -> None:
        await asyncio.sleep(0.5)

    harness.client.app.state.bus.subscribe(slow)  # type: ignore[attr-defined]
    with harness.connect() as ws:
        hello(ws)
        for i in range(5):
            send(ws, type="sensor", sensor="sensor.temperature", value=float(i))
        started = time.monotonic()
        send(ws, type="ping", id="fast")
        frame = receive(ws)
        while frame["type"] == "ping":
            frame = receive(ws)
        assert frame["id"] == "fast"
        assert time.monotonic() - started < 0.3
