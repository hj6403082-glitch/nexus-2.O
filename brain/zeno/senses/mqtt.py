"""MQTT as a sense, and the owner's MQTT configuration (``data/mqtt.json``).

``MqttSense`` subscribes to the topics the owner listed and turns each message into a
``DeviceEvent(device="mqtt", kind="sensor")`` on the bus, so Zigbee2MQTT or Home
Assistant values look like any other device's sensors. It also holds the connection
that actuator tools publish through. The broker password is never stored in the file:
``password_env`` names the environment variable that holds it.
"""

import asyncio
import contextlib
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

import aiomqtt
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from zeno.senses.events import DeviceEvent, EventBus
from zeno.senses.protocol import Capability

log = logging.getLogger(__name__)

DEVICE = "mqtt"


def _exact_topic(value: str) -> str:
    if any(char in value for char in "+#\x00"):
        raise ValueError("must be an exact topic, without wildcards")
    return value


Topic = Annotated[
    str, StringConstraints(min_length=1, max_length=256), AfterValidator(_exact_topic)
]
FieldName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
ActuatorName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,39}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _FieldSpec(_Strict):
    required: bool = True
    description: str = Field("", max_length=200)


class EnumField(_FieldSpec):
    type: Literal["enum"]
    values: list[Annotated[str, StringConstraints(min_length=1, max_length=64)]] = Field(
        min_length=1, max_length=32
    )


class NumberField(_FieldSpec):
    type: Literal["number"]
    min: float
    max: float
    integer: bool = False

    @model_validator(mode="after")
    def _ordered(self) -> "NumberField":
        if self.min > self.max:
            raise ValueError("min must not be above max")
        return self


class BoolField(_FieldSpec):
    type: Literal["bool"]


class StringField(_FieldSpec):
    type: Literal["string"]
    max_length: int = Field(64, ge=1, le=200)


PayloadField = Annotated[
    EnumField | NumberField | BoolField | StringField, Field(discriminator="type")
]


class Actuator(_Strict):
    name: ActuatorName
    description: str = Field(min_length=1, max_length=300)
    topic: Topic
    qos: Literal[0, 1, 2] = 1
    retain: bool = False
    payload: dict[FieldName, PayloadField] = Field(min_length=1, max_length=16)


class ReadTopic(_Strict):
    name: Capability
    topic: Topic


class Broker(_Strict):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(1883, ge=1, le=65535)
    username: str | None = Field(None, max_length=128)
    password_env: str | None = Field(None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    tls: bool = False
    client_id: str = Field("zeno-brain", min_length=1, max_length=64)


class MqttConfig(_Strict):
    broker: Broker
    read: list[ReadTopic] = Field(default_factory=list, max_length=64)
    actuators: list[Actuator] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def _unique_names(self) -> "MqttConfig":
        for kind, names in (
            ("read", [r.name for r in self.read]),
            ("actuator", [a.name for a in self.actuators]),
        ):
            if len(names) != len(set(names)):
                raise ValueError(f"{kind} names must be unique")
        return self


def load_mqtt_config(path: Path) -> MqttConfig | None:
    """The owner's MQTT setup, or None when the file does not exist."""
    if not path.exists():
        return None
    return MqttConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))


ClientFactory = Callable[..., Any]


class MqttSense:
    """Keeps one broker connection: listens to the read topics and carries publishes."""

    def __init__(
        self,
        config: MqttConfig,
        bus: EventBus,
        *,
        client_factory: ClientFactory = aiomqtt.Client,
        retry_delay: float = 1.0,
        max_retry_delay: float = 60.0,
        max_payload: int = 4096,
    ) -> None:
        self._config = config
        self._bus = bus
        self._factory = client_factory
        self._retry_delay = retry_delay
        self._max_retry_delay = max_retry_delay
        self._max_payload = max_payload
        self._names = {r.topic: r.name for r in config.read}
        self._client: Any = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="zeno-mqtt")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def publish(self, topic: str, payload: bytes, *, qos: int, retain: bool) -> None:
        client = self._client
        if client is None:
            raise ConnectionError("not connected to the MQTT broker")
        await client.publish(topic, payload, qos=qos, retain=retain)

    async def _run(self) -> None:
        delay = self._retry_delay
        while True:
            try:
                async with self._factory(**self._client_options()) as client:
                    self._client = client
                    delay = self._retry_delay
                    for topic in self._names:
                        await client.subscribe(topic, qos=1)
                    async for message in client.messages:
                        self._handle(str(message.topic), message.payload)
            except (aiomqtt.MqttError, OSError) as error:
                log.warning("MQTT broker %s: %s", self._config.broker.host, error)
            finally:
                self._client = None
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._max_retry_delay)

    def _client_options(self) -> dict[str, Any]:
        broker = self._config.broker
        password = os.environ.get(broker.password_env) if broker.password_env else None
        return {
            "hostname": broker.host,
            "port": broker.port,
            "username": broker.username,
            "password": password,
            "identifier": broker.client_id,
            "tls_params": aiomqtt.TLSParameters() if broker.tls else None,
        }

    def _handle(self, topic: str, payload: object) -> None:
        name = self._names.get(topic)
        if name is None:
            return
        if isinstance(payload, bytes | bytearray):
            if len(payload) > self._max_payload:
                return
            text = bytes(payload).decode("utf-8", errors="replace")
        else:
            text = "" if payload is None else str(payload)
        try:
            value: Any = json.loads(text)
        except ValueError:
            value = text
        self._bus.publish(
            DeviceEvent(DEVICE, "sensor", {"sensor": name, "value": value}, time.time())
        )
