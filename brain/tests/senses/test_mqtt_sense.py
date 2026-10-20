"""MqttSense: allowlisted MQTT topics become sensor events on the bus; it also publishes."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from zeno.senses.events import DeviceEvent, EventBus
from zeno.senses.mqtt import MqttConfig, MqttSense, load_mqtt_config


@dataclass
class Message:
    topic: str
    payload: bytes


@dataclass
class FakeClient:
    """Stands in for aiomqtt.Client: a context manager with subscribe/publish/messages."""

    broker: "FakeBroker"
    subscribed: list[str] = field(default_factory=list)

    async def __aenter__(self) -> "FakeClient":
        self.broker.connects += 1
        if self.broker.refuse > 0:
            self.broker.refuse -= 1
            raise OSError("connection refused")
        self.broker.client = self
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.broker.client = None

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        self.subscribed.append(topic)

    async def publish(self, topic: str, payload: bytes, qos: int = 0, retain: bool = False) -> None:
        self.broker.published.append((topic, payload, qos, retain))

    @property
    def messages(self) -> AsyncIterator[Message]:
        return self._messages()

    async def _messages(self) -> AsyncIterator[Message]:
        while True:
            message = await self.broker.inbox.get()
            if message is None:
                raise OSError("broker went away")
            yield message


@dataclass
class FakeBroker:
    refuse: int = 0
    connects: int = 0
    client: FakeClient | None = None
    options: dict[str, Any] = field(default_factory=dict)
    published: list[tuple[str, bytes, int, bool]] = field(default_factory=list)
    inbox: "asyncio.Queue[Message | None]" = field(default_factory=asyncio.Queue)

    def factory(self, **options: Any) -> FakeClient:
        self.options = options
        return FakeClient(self)


CONFIG = {
    "broker": {"host": "broker.lan", "port": 1884, "username": "zeno", "password_env": "MQ_PW"},
    "read": [{"name": "kitchen.temperature", "topic": "z2m/kitchen"}],
}


async def wait_for(condition: Any, seconds: float = 2.0) -> None:
    async with asyncio.timeout(seconds):
        while not condition():  # noqa: ASYNC110 (polls a fake's state)
            await asyncio.sleep(0.005)


@pytest.fixture
async def bus() -> AsyncIterator[EventBus]:
    bus = EventBus()
    await bus.start()
    yield bus
    await bus.stop()


def sense(bus: EventBus, broker: FakeBroker, **changes: Any) -> MqttSense:
    config = MqttConfig.model_validate({**CONFIG, **changes})
    return MqttSense(config, bus, client_factory=broker.factory, retry_delay=0.01)


async def test_subscribes_to_allowlisted_topics_and_publishes_events(
    bus: EventBus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MQ_PW", "secret")
    events: list[DeviceEvent] = []

    async def collect(event: DeviceEvent) -> None:
        events.append(event)

    bus.subscribe(collect, kind="sensor")
    broker = FakeBroker()
    mqtt = sense(bus, broker)
    await mqtt.start()
    try:
        await wait_for(lambda: broker.client is not None and broker.client.subscribed)
        assert broker.client is not None and broker.client.subscribed == ["z2m/kitchen"]
        assert broker.options["hostname"] == "broker.lan" and broker.options["port"] == 1884
        assert broker.options["password"] == "secret"  # noqa: S105 (a test value)
        await broker.inbox.put(Message("z2m/kitchen", b'{"temperature": 21.5}'))
        await broker.inbox.put(Message("z2m/kitchen", b"22"))
        await wait_for(lambda: len(events) == 2)
        assert events[0].device == "mqtt"
        assert events[0].data["sensor"] == "kitchen.temperature"
        assert events[0].data["value"] == {"temperature": 21.5}
        assert events[1].data["value"] == 22
    finally:
        await mqtt.stop()


async def test_unlisted_and_oversized_messages_are_dropped(bus: EventBus) -> None:
    events: list[DeviceEvent] = []

    async def collect(event: DeviceEvent) -> None:
        events.append(event)

    bus.subscribe(collect)
    broker = FakeBroker()
    mqtt = sense(bus, broker)
    await mqtt.start()
    try:
        await wait_for(lambda: broker.client is not None)
        await broker.inbox.put(Message("other/topic", b"1"))
        await broker.inbox.put(Message("z2m/kitchen", b"x" * 10_000))
        await broker.inbox.put(Message("z2m/kitchen", b"not json"))
        await wait_for(lambda: len(events) == 1)
        await asyncio.sleep(0.02)
        assert [e.data["value"] for e in events] == ["not json"]
    finally:
        await mqtt.stop()


async def test_reconnects_after_the_broker_drops(bus: EventBus) -> None:
    broker = FakeBroker(refuse=2)
    mqtt = sense(bus, broker)
    await mqtt.start()
    try:
        await wait_for(lambda: broker.client is not None)
        await broker.inbox.put(None)
        await wait_for(lambda: broker.connects >= 4 and broker.client is not None)
    finally:
        await mqtt.stop()


async def test_publish_goes_out_through_the_live_connection(bus: EventBus) -> None:
    broker = FakeBroker()
    mqtt = sense(bus, broker)
    with pytest.raises(ConnectionError):
        await mqtt.publish("home/x", b"1", qos=0, retain=False)
    await mqtt.start()
    try:
        await wait_for(lambda: broker.client is not None)
        await mqtt.publish("home/x", b"1", qos=1, retain=False)
        assert broker.published == [("home/x", b"1", 1, False)]
    finally:
        await mqtt.stop()


def test_config_file_is_optional_and_never_holds_a_password(tmp_path: Path) -> None:
    assert load_mqtt_config(tmp_path / "missing.json") is None
    path = tmp_path / "mqtt.json"
    path.write_text(json.dumps({"broker": {"host": "h", "password": "oops"}}))
    with pytest.raises(ValueError):
        load_mqtt_config(path)
    path.write_text(json.dumps(CONFIG))
    loaded = load_mqtt_config(path)
    assert loaded is not None and loaded.broker.host == "broker.lan"
