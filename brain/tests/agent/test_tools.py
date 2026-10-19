"""Tool definitions: explicit, typed, documented Python callables."""

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from tests.agent.conftest import AddArgs, Toolbox
from zeno.agent.tools.base import Risk, Tool, ToolArgs, ToolDefinitionError, tool


def test_decorator_builds_a_tool_with_metadata(toolbox: Toolbox) -> None:
    add = toolbox.add
    assert isinstance(add, Tool)
    assert add.name == "add"
    assert add.description == "Add two integers."
    assert add.args_model is AddArgs
    assert add.risk is Risk.READ_ONLY
    assert add.timeout == 1.0


def test_name_can_be_given_explicitly() -> None:
    @tool("sum_two", risk=Risk.READ_ONLY)
    async def anything(args: AddArgs) -> str:
        """Add two integers."""
        return str(args.a + args.b)

    assert anything.name == "sum_two"


async def test_invoke_runs_the_function_with_validated_args(toolbox: Toolbox) -> None:
    assert await toolbox.add.invoke(AddArgs(a=2, b=3)) == "5"
    assert toolbox.calls == [("add", {"a": 2, "b": 3})]


def test_args_models_forbid_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AddArgs.model_validate({"a": 1, "b": 2, "c": 3})
    assert AddArgs.model_json_schema()["additionalProperties"] is False


def test_risk_must_be_declared() -> None:
    with pytest.raises(TypeError):

        @tool()  # type: ignore[call-arg]
        async def no_risk(args: AddArgs) -> str:
            """Docs."""
            return ""


def test_a_docstring_is_required() -> None:
    with pytest.raises(ToolDefinitionError, match="docstring"):

        @tool(risk=Risk.READ_ONLY)
        async def undocumented(args: AddArgs) -> str:
            return ""


def test_tools_must_be_async() -> None:
    with pytest.raises(ToolDefinitionError, match="async"):

        @tool(risk=Risk.READ_ONLY)  # type: ignore[arg-type]
        def blocking(args: AddArgs) -> str:
            """Docs."""
            return ""


class LooseArgs(BaseModel):
    a: int


@pytest.mark.parametrize(
    "annotation",
    [LooseArgs, int, dict[str, Any], None],
    ids=["plain-basemodel", "int", "dict", "missing"],
)
def test_the_single_parameter_must_be_a_toolargs_model(annotation: Any) -> None:
    async def func(args):  # type: ignore[no-untyped-def]
        """Docs."""
        return ""

    if annotation is not None:
        func.__annotations__ = {"args": annotation, "return": str}
    else:
        func.__annotations__ = {"return": str}
    with pytest.raises(ToolDefinitionError, match="ToolArgs"):
        tool(risk=Risk.READ_ONLY)(func)


def test_exactly_one_parameter() -> None:
    with pytest.raises(ToolDefinitionError, match="one parameter"):

        @tool(risk=Risk.READ_ONLY)  # type: ignore[arg-type]
        async def two(args: AddArgs, extra: int) -> str:
            """Docs."""
            return ""


def test_must_return_str() -> None:
    with pytest.raises(ToolDefinitionError, match="str"):

        @tool(risk=Risk.READ_ONLY)  # type: ignore[arg-type]
        async def number(args: AddArgs) -> int:
            """Docs."""
            return 1


@pytest.mark.parametrize("name", ["Add", "1add", "add-two", "a", "x" * 49, "rm -rf"])
def test_names_are_simple_identifiers(name: str) -> None:
    with pytest.raises(ToolDefinitionError, match="name"):

        @tool(name, risk=Risk.READ_ONLY)
        async def func(args: AddArgs) -> str:
            """Docs."""
            return ""


@pytest.mark.parametrize("timeout", [0, -1])
def test_timeout_must_be_positive(timeout: float) -> None:
    with pytest.raises(ToolDefinitionError, match="timeout"):

        @tool(risk=Risk.READ_ONLY, timeout=timeout)
        async def func(args: AddArgs) -> str:
            """Docs."""
            return ""


def test_toolargs_are_immutable() -> None:
    args = AddArgs(a=1, b=2)
    with pytest.raises(ValidationError):
        args.a = 5


class _Empty(ToolArgs):
    pass


def test_tools_without_arguments_use_an_empty_model() -> None:
    @tool(risk=Risk.READ_ONLY)
    async def ping(args: _Empty) -> str:
        """Answer pong."""
        return "pong"

    assert ping.args_model.model_json_schema()["properties"] == {}
