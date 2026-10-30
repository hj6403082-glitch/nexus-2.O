"""MQTT tools: owner-declared actuators with bounded payloads, and allowlisted reads."""

import json
import time
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import ValidationError

from zeno.agent.tools.base import Risk, Tool
from zeno.agent.tools.devices import SensorCache
from zeno.agent.tools.mqtt import actuator_args_model, mqtt_tools
from zeno.inference.grammar import gbnf_for_model
from zeno.senses.events import DeviceEvent
from zeno.senses.mqtt import MqttConfig

CONFIG: dict[str, Any] = {
    "broker": {"host": "127.0.0.1"},
    "read": [
        {"name": "kitchen.temperature", "topic": "zigbee2mqtt/kitchen_sensor"},
        {"name": "door.state", "topic": "home/door"},
    ],
    "actuators": [
        {
            "name": "kitchen_light",
            "description": "The kitchen ceiling light.",
            "topic": "zigbee2mqtt/kitchen_light/set",
            "qos": 1,
            "payload": {
                "state": {"type": "enum", "values": ["ON", "OFF"]},
                "brightness": {
                    "type": "number",
                    "min": 0,
                    "max": 254,
                    "integer": True,
                    "required": False,
                },
            },
        },
        {
            "name": "thermostat",
            "description": "Heating set point.",
            "topic": "home/thermostat/set",
            "payload": {
                "celsius": {"type": "number", "min": 5, "max": 30},
                "away": {"type": "bool", "required": False},
                "note": {"type": "string", "max_length": 20, "required": False},
            },
        },
    ],
}


@dataclass
class FakeLink:
    sent: list[tuple[str, bytes, int, bool]] = field(default_factory=list)
    fail: Exception | None = None

    async def publish(self, topic: str, payload: bytes, *, qos: int, retain: bool) -> None:
        if self.fail is not None:
            raise self.fail
        self.sent.append((topic, payload, qos, retain))


def config(**changes: Any) -> MqttConfig:
    return MqttConfig.model_validate({**CONFIG, **changes})


def tools(link: FakeLink | None = None, sensors: SensorCache | None = None) -> dict[str, Tool[Any]]:
    found = mqtt_tools(config(), link or FakeLink(), sensors or SensorCache())
    return {t.name: t for t in found}


def call_args(tool: Tool[Any], **values: Any) -> Any:
    return tool.args_model.model_validate(values)


# --- configuration ------------------------------------------------------------------


def test_one_tool_per_actuator_plus_a_reader() -> None:
    found = tools()
    assert sorted(found) == ["actuate_kitchen_light", "actuate_thermostat", "mqtt_read"]
    assert found["actuate_kitchen_light"].risk is Risk.MUTATING
    assert found["mqtt_read"].risk is Risk.READ_ONLY
    assert found["actuate_kitchen_light"].description.startswith("The kitchen ceiling light.")


def test_no_reader_without_read_topics_and_no_actuators_without_declarations() -> None:
    assert mqtt_tools(config(read=[], actuators=[]), FakeLink(), SensorCache()) == []


@pytest.mark.parametrize("topic", ["home/#", "home/+/set", "", "a\x00b", "x" * 300])
def test_topics_are_exact_and_bounded(topic: str) -> None:
    with pytest.raises(ValidationError):
        config(read=[{"name": "a.b", "topic": topic}])


@pytest.mark.parametrize(
    "payload",
    [
        {"x": {"type": "number", "min": 5, "max": 1}},
        {"x": {"type": "enum", "values": []}},
        {"x": {"type": "string", "max_length": 5000}},
        {"x": {"type": "object"}},
        {"Bad-Name": {"type": "bool"}},
    ],
)
def test_payload_schemas_are_a_small_checked_subset(payload: dict[str, Any]) -> None:
    actuator = {"name": "thing", "description": "A thing.", "topic": "t", "payload": payload}
    with pytest.raises(ValidationError):
        config(actuators=[actuator])


def test_duplicate_actuator_names_are_refused() -> None:
    actuator = CONFIG["actuators"][0]
    with pytest.raises(ValidationError, match="unique"):
        config(actuators=[actuator, actuator])


# --- payload bounds -----------------------------------------------------------------


def test_actuator_arguments_are_bounded() -> None:
    tool = tools()["actuate_kitchen_light"]
    assert call_args(tool, state="ON", brightness=254).brightness == 254
    for bad in (
        {"state": "DIM"},
        {"state": "ON", "brightness": 900},
        {"brightness": 3},
        {"state": "ON", "colour": "red"},
        {"state": "ON", "brightness": 1.5},
    ):
        with pytest.raises(ValidationError):
            call_args(tool, **bad)


def test_small_integer_ranges_are_held_by_the_grammar_itself() -> None:
    spec = config().actuators[0]
    grammar = gbnf_for_model(actuator_args_model(spec))
    assert '"254"' in grammar and '"255"' not in grammar
    assert '\\"ON\\"' in grammar and '\\"OFF\\"' in grammar


def test_float_and_string_bounds_hold() -> None:
    tool = tools()["actuate_thermostat"]
    assert call_args(tool, celsius=21.5).celsius == 21.5
    for bad in ({"celsius": 40}, {"celsius": 21, "note": "x" * 21}, {"celsius": 21, "away": "yes"}):
        with pytest.raises(ValidationError):
            call_args(tool, **bad)


# --- publishing ---------------------------------------------------------------------


async def test_actuating_publishes_only_the_given_fields() -> None:
    link = FakeLink()
    tool = tools(link)["actuate_kitchen_light"]
    text = await tool.invoke(call_args(tool, state="ON"))
    assert link.sent == [("zigbee2mqtt/kitchen_light/set", b'{"state":"ON"}', 1, False)]
    assert "kitchen_light" in text and "sent" in text


async def test_a_broker_failure_is_readable() -> None:
    tool = tools(FakeLink(fail=ConnectionError("not connected to the MQTT broker")))[
        "actuate_thermostat"
    ]
    with pytest.raises(ValueError, match="could not reach"):
        await tool.invoke(call_args(tool, celsius=20))


# --- reading ------------------------------------------------------------------------


def test_reads_name_only_allowlisted_values() -> None:
    tool = tools()["mqtt_read"]
    assert call_args(tool, name="door.state").name == "door.state"
    with pytest.raises(ValidationError):
        call_args(tool, name="zigbee2mqtt/kitchen_sensor")


async def test_reading_returns_the_latest_value() -> None:
    sensors = SensorCache()
    data = {"sensor": "kitchen.temperature", "value": {"temperature": 21.4, "humidity": 40}}
    await sensors.handle(DeviceEvent("mqtt", "sensor", data, time.time()))
    tool = tools(sensors=sensors)["mqtt_read"]
    text = await tool.invoke(call_args(tool, name="kitchen.temperature"))
    assert json.dumps({"temperature": 21.4, "humidity": 40}) in text or "21.4" in text


async def test_reading_before_any_message_says_so() -> None:
    tool = tools()["mqtt_read"]
    assert "No message" in await tool.invoke(call_args(tool, name="door.state"))
