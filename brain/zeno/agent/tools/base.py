"""Tool definitions: explicitly registered, typed and documented async callables."""

import inspect
import re
import typing
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

NAME = re.compile(r"^[a-z][a-z0-9_]{1,47}$")


class Risk(StrEnum):
    READ_ONLY = "read_only"
    """Only looks: runs without asking."""
    MUTATING = "mutating"
    """Changes something: needs the owner's explicit approval every time."""


class ToolArgs(BaseModel):
    """Base for every tool's arguments: unknown fields are refused, values are frozen."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolDefinitionError(Exception):
    """A tool was defined or registered incorrectly (a programming error)."""


A = TypeVar("A", bound=ToolArgs)


@dataclass(frozen=True, slots=True, eq=False)
class Tool(Generic[A]):
    name: str
    description: str
    args_model: type[A]
    risk: Risk
    timeout: float
    func: Callable[[A], Awaitable[str]]

    async def invoke(self, args: A) -> str:
        return await self.func(args)


def tool(
    name: str | None = None, *, risk: Risk, timeout: float = 10.0
) -> Callable[[Callable[[A], Awaitable[str]]], Tool[A]]:
    """Turn ``async def name(args: SomeArgs) -> str`` into a ``Tool``.

    The docstring is the description the model reads, the single parameter's
    ``ToolArgs`` model is the argument schema, and ``risk`` must be stated.
    """

    def decorate(func: Callable[[A], Awaitable[str]]) -> Tool[A]:
        tool_name = name if name is not None else str(getattr(func, "__name__", ""))
        if not NAME.fullmatch(tool_name):
            raise ToolDefinitionError(
                f"Tool name {tool_name!r} must be 2-48 lowercase letters, digits or underscores."
            )
        if not inspect.iscoroutinefunction(func):
            raise ToolDefinitionError(f"Tool {tool_name} must be an async function.")
        description = inspect.getdoc(func)
        if not description:
            raise ToolDefinitionError(f"Tool {tool_name} needs a docstring; the model reads it.")
        if timeout <= 0:
            raise ToolDefinitionError(f"Tool {tool_name} needs a positive timeout.")
        # _args_model checked at runtime that the annotation is func's own args model.
        args_model = typing.cast("type[A]", _args_model(tool_name, func))
        return Tool(tool_name, description, args_model, risk, timeout, func)

    return decorate


def _args_model(name: str, func: Callable[..., object]) -> type[ToolArgs]:
    parameters = list(inspect.signature(func).parameters)
    if len(parameters) != 1:
        raise ToolDefinitionError(f"Tool {name} must take exactly one parameter (its ToolArgs).")
    hints = typing.get_type_hints(func)
    annotation = hints.get(parameters[0])
    if not (isinstance(annotation, type) and _is_args_model(annotation)):
        raise ToolDefinitionError(
            f"Tool {name}'s parameter must be annotated with a ToolArgs model."
        )
    if hints.get("return") is not str:
        raise ToolDefinitionError(f"Tool {name} must return str.")
    return annotation


def _is_args_model(annotation: object) -> bool:
    try:
        return isinstance(annotation, type) and issubclass(annotation, ToolArgs)
    except TypeError:  # generic aliases such as dict[str, int]
        return False
