"""MQTT tools: one ``actuate_<name>`` per actuator the owner declared, and ``mqtt_read``.

Actuator payloads use a small schema subset (enum, bounded number, bool, short
string) compiled into a Pydantic model, so arguments outside the owner's bounds fail
validation, and enums and small integer ranges cannot even be generated.
"""

import dataclasses
import json
import math
import typing
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol

from pydantic import Field, create_model

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool
from zeno.agent.tools.devices import SensorCache
from zeno.senses.mqtt import (
    DEVICE,
    Actuator,
    BoolField,
    EnumField,
    MqttConfig,
    NumberField,
    PayloadField,
)

# Integer ranges up to this many values are listed in the schema as an enum, which the
# grammar enforces; wider ranges are checked by validation alone.
_ENUM_RANGE_LIMIT = 256


class MqttLink(Protocol):
    async def publish(self, topic: str, payload: bytes, *, qos: int, retain: bool) -> None: ...


class ActuatorArgs(ToolArgs):
    pass


class ReadArgs(ToolArgs):
    name: str


def _literal(values: typing.Iterable[str | int]) -> Any:
    return typing.cast("Any", Literal).__getitem__(tuple(values))


def _field_type(spec: PayloadField) -> Any:
    about = spec.description or None
    if isinstance(spec, EnumField):
        return Annotated[_literal(spec.values), Field(description=about)]
    if isinstance(spec, BoolField):
        return Annotated[bool, Field(strict=True, description=about)]
    if isinstance(spec, NumberField):
        if spec.integer:
            low, high = math.ceil(spec.min), math.floor(spec.max)
            if high - low < _ENUM_RANGE_LIMIT:
                return Annotated[_literal(range(low, high + 1)), Field(description=about)]
            return Annotated[int, Field(ge=low, le=high, strict=True, description=about)]
        return Annotated[float, Field(ge=spec.min, le=spec.max, description=about)]
    return Annotated[str, Field(max_length=spec.max_length, description=about)]


def actuator_args_model(actuator: Actuator) -> type[ActuatorArgs]:
    """The argument model for one actuator's payload."""
    fields: dict[str, Any] = {}
    for name, spec in actuator.payload.items():
        kind = _field_type(spec)
        fields[name] = (kind, ...) if spec.required else (kind | None, None)
    model_name = "Actuate" + actuator.name.title().replace("_", "") + "Args"
    return create_model(model_name, __base__=ActuatorArgs, **fields)


def mqtt_tools(config: MqttConfig, link: MqttLink, sensors: SensorCache) -> list[Tool[Any]]:
    tools: list[Tool[Any]] = [_actuator_tool(a, link) for a in config.actuators]
    if config.read:
        tools.append(_read_tool([r.name for r in config.read], sensors))
    return tools


def _actuator_tool(actuator: Actuator, link: MqttLink) -> Tool[Any]:
    async def actuate(args: ActuatorArgs) -> str:
        payload = json.dumps(args.model_dump(exclude_none=True), separators=(",", ":"))
        try:
            await link.publish(
                actuator.topic, payload.encode(), qos=actuator.qos, retain=actuator.retain
            )
        except (ConnectionError, OSError) as error:
            raise ValueError(f"could not reach the MQTT broker: {error}") from error
        return f"{actuator.name}: sent {payload}"

    actuate.__name__ = f"actuate_{actuator.name}"
    actuate.__doc__ = actuator.description
    built = tool(risk=Risk.MUTATING, timeout=5.0)(actuate)
    return dataclasses.replace(built, args_model=actuator_args_model(actuator))


def _read_tool(names: list[str], sensors: SensorCache) -> Tool[Any]:
    @tool(risk=Risk.READ_ONLY, timeout=2.0)
    async def mqtt_read(args: ReadArgs) -> str:
        """Read the latest value from one of the owner's MQTT topics (home sensors)."""
        reading = sensors.latest(DEVICE, args.name)
        if reading is None:
            return f"No message on {args.name} yet."
        when = datetime.fromtimestamp(reading.received_at).astimezone()
        value = json.dumps(reading.value) if not isinstance(reading.value, str) else reading.value
        return f"{args.name} = {value} (at {when.isoformat(timespec='seconds')})"

    model = create_model(
        "MqttReadArgs",
        __base__=ReadArgs,
        name=(_literal(names), Field(description=f"One of: {', '.join(names)}.")),
    )
    return dataclasses.replace(mqtt_read, args_model=model)
