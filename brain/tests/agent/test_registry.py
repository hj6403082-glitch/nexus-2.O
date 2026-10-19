"""ToolRegistry: the explicit allowlist of what the agent can call."""

from typing import Any

import pytest

from tests.agent.conftest import AddArgs, Toolbox
from zeno.agent.registry import ToolRegistry, UnknownToolError
from zeno.agent.tools.base import Risk, ToolDefinitionError, tool


def test_register_and_look_up(toolbox: Toolbox) -> None:
    registry = ToolRegistry()
    registry.register(toolbox.add)
    assert registry.get("add") is toolbox.add
    assert "add" in registry
    assert registry.names() == ["add"]
    assert len(registry) == 1


def test_lookup_of_an_unknown_tool_raises(registry: ToolRegistry) -> None:
    with pytest.raises(UnknownToolError):
        registry.get("format_disk")


def test_duplicate_names_are_rejected(toolbox: Toolbox) -> None:
    registry = ToolRegistry([toolbox.add])

    @tool("add", risk=Risk.MUTATING)
    async def other(args: AddArgs) -> str:
        """Another add."""
        return ""

    with pytest.raises(ToolDefinitionError, match="already registered"):
        registry.register(other)
    assert registry.get("add") is toolbox.add


@pytest.mark.parametrize(
    "thing",
    ["os.system", "zeno.agent.tools.clock:get_time", print, lambda args: "x"],
    ids=["module-path", "import-string", "builtin", "lambda"],
)
def test_only_tool_objects_can_be_registered(thing: Any) -> None:
    # No dynamic imports and no raw callables: a tool exists only if code built
    # it with @tool.
    with pytest.raises(TypeError):
        ToolRegistry().register(thing)


def test_iterates_in_registration_order(toolbox: Toolbox) -> None:
    registry = ToolRegistry([toolbox.set_light, toolbox.add])
    assert [t.name for t in registry] == ["set_light", "add"]


def test_instructions_describe_every_tool_and_its_risk(registry: ToolRegistry) -> None:
    text = registry.instructions()
    for name in ("add", "set_light", "slow", "explode"):
        assert name in text
    assert "Add two integers." in text
    set_light_line = next(line for line in text.splitlines() if "set_light" in line)
    assert "approval" in set_light_line
    add_line = next(line for line in text.splitlines() if line.startswith("- add"))
    assert "approval" not in add_line
    # The argument schema is spelled out so the model knows what to send.
    assert '"room"' in text and '"on"' in text


def test_instructions_are_stable(toolbox: Toolbox) -> None:
    # Byte-stable prompts keep llama.cpp's prompt cache warm.
    assert ToolRegistry(toolbox.all()).instructions() == ToolRegistry(toolbox.all()).instructions()
