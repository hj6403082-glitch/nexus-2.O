"""Build syntax trees in the JSON shape ps_parse.ps1 prints, so the PowerShell policy
can be tested on any machine. tests/windows/test_ps_parse.py checks the same commands
through PowerShell's real parser wherever ``pwsh`` or ``powershell`` is installed."""

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class N:
    type: str
    children: list["N"] = field(default_factory=list)
    props: dict[str, str] = field(default_factory=dict)
    text: str = ""


def s(value: str, kind: str = "BareWord") -> N:
    return N(
        "StringConstantExpressionAst",
        props={"Value": value, "StringConstantType": kind},
        text=value,
    )


def q(value: str) -> N:
    return s(value, "SingleQuoted")


def num(value: int) -> N:
    return N("ConstantExpressionAst", props={"Value": str(value)}, text=str(value))


def var(path: str, *, splatted: bool = False) -> N:
    return N(
        "VariableExpressionAst",
        props={"VariablePath": path, "Splatted": str(splatted)},
        text="$" + path,
    )


def xs(value: str, *parts: N) -> N:
    return N(
        "ExpandableStringExpressionAst",
        list(parts),
        {"Value": value, "StringConstantType": "DoubleQuoted"},
        f'"{value}"',
    )


def arr(*items: N) -> N:
    return N("ArrayLiteralAst", list(items))


def p(name: str, argument: N | None = None) -> N:
    return N(
        "CommandParameterAst", [argument] if argument else [], {"ParameterName": name}, "-" + name
    )


def cmd(name: str | N, *args: N, op: str = "Unknown") -> N:
    head = s(name) if isinstance(name, str) else name
    props = {"InvocationOperator": op}
    if isinstance(name, str):
        props["CommandName"] = name
    return N("CommandAst", [head, *args], props, name if isinstance(name, str) else "")


def expr(inner: N) -> N:
    return N("CommandExpressionAst", [inner])


def pipe(*elements: N, background: bool = False) -> N:
    return N("PipelineAst", list(elements), {"Background": str(background)})


def named(*statements: N) -> N:
    return N("NamedBlockAst", list(statements), {"BlockKind": "End", "Unnamed": "True"})


def script(*statements: N) -> N:
    return N("ScriptBlockAst", [named(*statements)])


def block(*statements: N) -> N:
    return N("ScriptBlockExpressionAst", [script(*statements)])


def member(target: N, name: str, *, static: bool = False) -> N:
    return N("MemberExpressionAst", [target, s(name)], {"Static": str(static)})


def call(target: N, name: str, *args: N) -> N:
    return N("InvokeMemberExpressionAst", [target, s(name), *args], {"Static": "False"})


def binop(left: N, operator: str, right: N) -> N:
    return N("BinaryExpressionAst", [left, right], {"Operator": operator})


def other(kind: str, *children: N, **props: str) -> N:
    return N(kind, list(children), dict(props))


def one(*elements: N) -> N:
    """A whole command: one pipeline of these elements."""
    return script(pipe(*elements))


def dump(root: N, *, errors: list[str] | None = None, aliases: dict[str, str] | None = None) -> str:
    nodes: list[dict[str, Any]] = []

    def visit(node: N, parent: int) -> None:
        index = len(nodes)
        entry: dict[str, Any] = {
            "id": index,
            "parent": parent,
            "type": node.type,
            "start": index,
            "end": index + 1,
            "text": node.text,
            "props": node.props,
        }
        nodes.append(entry)
        for child in node.children:
            visit(child, index)

    visit(root, -1)
    return json.dumps({"errors": errors or [], "nodes": nodes, "aliases": aliases or {}})
