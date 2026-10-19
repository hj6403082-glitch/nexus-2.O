"""UI tools: the agent drives the web app through validated commands."""

import re
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from zeno.agent.tools.base import Risk
from zeno.agent.tools.ui import (
    MODULES,
    FormArgs,
    ModuleArgs,
    MotionArgs,
    NoUiArgs,
    RotateArgs,
    ui_tools,
)

MODULES_TS = Path(__file__).parents[3] / "src" / "lib" / "modules.ts"


@pytest.fixture
def sent() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def tools(sent: list[dict[str, Any]]) -> dict[str, Any]:
    async def emit(command: dict[str, Any]) -> None:
        sent.append(command)

    return {t.name: t for t in ui_tools(emit)}


async def test_each_tool_emits_the_web_apps_command_shape(
    tools: dict[str, Any], sent: list[dict[str, Any]]
) -> None:
    await tools["open_module"].invoke(ModuleArgs(module="weather"))
    await tools["close_module"].invoke(NoUiArgs())
    await tools["transform_form"].invoke(FormArgs(form="human"))
    await tools["rotate_view"].invoke(RotateArgs(direction="left"))
    await tools["set_motion"].invoke(MotionArgs(enabled=False))
    assert sent == [
        {"type": "open", "module": "weather"},
        {"type": "close"},
        {"type": "transform", "form": "human"},
        {"type": "rotate", "direction": "left"},
        {"type": "motion", "enabled": False},
    ]


async def test_tools_confirm_what_they_did(tools: dict[str, Any]) -> None:
    assert "weather" in await tools["open_module"].invoke(ModuleArgs(module="weather"))


def test_unknown_modules_are_refused() -> None:
    with pytest.raises(ValidationError):
        ModuleArgs(module="bank-account")  # type: ignore[arg-type]


def test_ui_tools_only_change_the_screen(tools: dict[str, Any]) -> None:
    # They move what is displayed, which the owner can undo at a glance, so they
    # run without an approval prompt.
    assert {t.risk for t in tools.values()} == {Risk.READ_ONLY}


@pytest.mark.skipif(not MODULES_TS.is_file(), reason="web app sources not present")
def test_module_list_matches_the_web_app() -> None:
    ids = re.findall(r"\{ id: '([a-z]+)'", MODULES_TS.read_text(encoding="utf-8"))
    assert ids, "could not read module ids from src/lib/modules.ts"
    assert set(get_args(MODULES)) == set(ids)
