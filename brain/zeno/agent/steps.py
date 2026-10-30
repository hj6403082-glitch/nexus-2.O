"""The shape of one ReAct step, built from the registry so the grammar only allows
registered tools with arguments that match their schemas."""

from functools import lru_cache
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel, create_model

from zeno.agent.registry import ToolRegistry
from zeno.agent.tools.base import ToolArgs
from zeno.inference.grammar import gbnf_for_model


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolInvocation(_Strict):
    tool: str
    args: ToolArgs


class ActionStep(_Strict):
    """Field order is generation order: the model reasons, then acts."""

    thought: str
    action: ToolInvocation


class FinalStep(_Strict):
    thought: str
    final: str


def step_model(registry: ToolRegistry) -> type[RootModel[Any]]:
    """A root model that parses one step for the registry's current tools.

    ``.root`` of a parsed value is a ``FinalStep`` or an ``ActionStep`` whose
    ``action.args`` is an instance of that tool's own args model.
    """
    return _build(_signature(registry))


def step_grammar(registry: ToolRegistry) -> str:
    return gbnf_for_model(step_model(registry))


def _signature(registry: ToolRegistry) -> tuple[tuple[str, type[ToolArgs]], ...]:
    return tuple((item.name, item.args_model) for item in registry)


@lru_cache(maxsize=32)
def _build(tools: tuple[tuple[str, type[ToolArgs]], ...]) -> type[RootModel[Any]]:
    if not tools:
        return RootModel[FinalStep]
    calls: list[type[ToolInvocation]] = [
        create_model(
            f"Call_{name}",
            __base__=ToolInvocation,
            tool=(Literal[name], ...),  # type: ignore[arg-type]  # a runtime-built Literal
            args=(args_model, ...),
        )
        for name, args_model in tools
    ]
    # Typing below is dynamic by nature: the union is assembled from the registry.
    action_type: Any = (
        calls[0] if len(calls) == 1 else Annotated[Union[tuple(calls)], Field(discriminator="tool")]  # noqa: UP007
    )
    action_step = create_model("ActionStep", __base__=ActionStep, action=(action_type, ...))
    root: Any = RootModel[Union[action_step, FinalStep]]  # noqa: UP007
    return root  # type: ignore[no-any-return]
