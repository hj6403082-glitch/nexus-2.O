"""UI tools: change what the web app shows, through its own command shapes.

These only move what is on screen, which the owner sees and can undo at once, so
they are READ_ONLY in the approval sense: they change nothing on the computer.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool

# Mirrors src/lib/modules.ts (tests/agent/test_ui_tools.py checks they match).
MODULES = Literal[
    "instagram",
    "stocks",
    "projects",
    "sports",
    "calendar",
    "weather",
    "ai",
    "news",
    "music",
    "system",
]

Emit = Callable[[dict[str, Any]], Awaitable[None]]


class NoUiArgs(ToolArgs):
    pass


class ModuleArgs(ToolArgs):
    module: MODULES


class FormArgs(ToolArgs):
    form: Literal["human", "spatial"]


class RotateArgs(ToolArgs):
    direction: Literal["left", "right"]


class MotionArgs(ToolArgs):
    enabled: bool


def ui_tools(emit: Emit) -> list[Tool[Any]]:
    """Tools bound to one client: ``emit`` sends a command to that client's screen."""

    @tool(risk=Risk.READ_ONLY, timeout=2.0)
    async def open_module(args: ModuleArgs) -> str:
        """Open one of the web app's modules on screen."""
        await emit({"type": "open", "module": args.module})
        return f"Opened the {args.module} module."

    @tool(risk=Risk.READ_ONLY, timeout=2.0)
    async def close_module(args: NoUiArgs) -> str:
        """Close the open module and return to the orbit view."""
        await emit({"type": "close"})
        return "Closed the module."

    @tool(risk=Risk.READ_ONLY, timeout=2.0)
    async def transform_form(args: FormArgs) -> str:
        """Change Zeno's on-screen form to human or spatial."""
        await emit({"type": "transform", "form": args.form})
        return f"Switched to the {args.form} form."

    @tool(risk=Risk.READ_ONLY, timeout=2.0)
    async def rotate_view(args: RotateArgs) -> str:
        """Rotate the module orbit left or right."""
        await emit({"type": "rotate", "direction": args.direction})
        return f"Rotated {args.direction}."

    @tool(risk=Risk.READ_ONLY, timeout=2.0)
    async def set_motion(args: MotionArgs) -> str:
        """Turn the ambient drift of the orbit on or off."""
        await emit({"type": "motion", "enabled": args.enabled})
        return f"Motion {'on' if args.enabled else 'off'}."

    return [open_module, close_module, transform_form, rotate_view, set_motion]
