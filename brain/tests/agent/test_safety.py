"""Static guarantees about the agent package's source code."""

import ast
from pathlib import Path

import pytest

import zeno.agent

AGENT_DIR = Path(zeno.agent.__file__).parent
ZENO_DIR = AGENT_DIR.parent
# The agent, the OS back ends its tools drive, and the multimodal workers its tools feed.
SOURCES = sorted(
    [
        *AGENT_DIR.rglob("*.py"),
        *(ZENO_DIR / "hostos").rglob("*.py"),
        *(ZENO_DIR / "multimodal").rglob("*.py"),
    ]
)
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


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(ZENO_DIR)))
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


def test_only_the_script_runner_and_the_command_runner_start_processes() -> None:
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
                starters.add(path.relative_to(ZENO_DIR).as_posix())
    assert starters == {"agent/tools/scripts.py", "hostos/process.py"}


def test_the_command_runner_only_ever_uses_exec_without_a_shell() -> None:
    tree = ast.parse((ZENO_DIR / "hostos" / "process.py").read_text(encoding="utf-8"))
    process_calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in PROCESS_CALLS | {"create_subprocess_shell", "system", "popen"}:
                process_calls.add(node.func.attr)
            assert all(k.arg != "shell" for k in node.keywords)
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            assert "subprocess" not in names
    assert process_calls == {"create_subprocess_exec"}


# Modules that open connections beyond this PC, and the only files allowed to use them.
OUTBOUND = {
    "httpx": {"agent/tools/web.py"},
    "httpcore": {"agent/tools/web.py"},
    "icmplib": {"agent/tools/network.py"},
    "asyncssh": {"agent/tools/ssh.py"},
    "aiomqtt": {"senses/mqtt.py"},
    "dbus_fast": {"hostos/linux/dbus.py"},
    "paramiko": set(),
    "requests": set(),
    "urllib": set(),
    "aiohttp": set(),
}


def test_outbound_network_libraries_stay_in_their_own_modules() -> None:
    users: dict[str, set[str]] = {name: set() for name in OUTBOUND}
    for path in sorted(ZENO_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                if root in users:
                    users[root].add(path.relative_to(ZENO_DIR).as_posix())
    assert users == OUTBOUND
