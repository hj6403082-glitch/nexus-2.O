"""Static guarantees about the agent package's source code."""

import ast
from pathlib import Path

import pytest

import zeno.agent

AGENT_DIR = Path(zeno.agent.__file__).parent
SOURCES = sorted(AGENT_DIR.rglob("*.py"))
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_MODULES = {"importlib", "pickle", "marshal", "ctypes"}
FORBIDDEN_ATTRIBUTES = {
    ("os", "system"),
    ("os", "popen"),
    ("os", "execv"),
    ("os", "spawnl"),
    ("asyncio", "create_subprocess_shell"),
}
PROCESS_CALLS = {"create_subprocess_exec", "Popen", "run", "call", "check_output"}


def test_sources_were_found() -> None:
    assert len(SOURCES) >= 5


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(AGENT_DIR)))
def test_no_dynamic_code_or_shell(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id not in FORBIDDEN_CALLS, f"{path.name}: {func.id}()"
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                assert (func.value.id, func.attr) not in FORBIDDEN_ATTRIBUTES, path.name
            for keyword in node.keywords:
                is_shell = keyword.arg == "shell"
                assert not is_shell, f"{path.name}: shell= is never allowed"
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in FORBIDDEN_MODULES, path.name
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in FORBIDDEN_MODULES, path.name


def test_only_the_script_runner_starts_processes() -> None:
    starters = set()
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"asyncio", "subprocess"}
                and node.func.attr in PROCESS_CALLS
            ):
                starters.add(path.relative_to(AGENT_DIR).as_posix())
    assert starters == {"tools/scripts.py"}
