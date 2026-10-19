"""Step schema and grammar: the model can only emit well-formed, known tool calls."""

import json

import pytest
from llama_cpp import LlamaGrammar
from pydantic import ValidationError

from tests.agent.conftest import AddArgs, LightArgs, Toolbox, act, final
from zeno.agent.registry import ToolRegistry
from zeno.agent.steps import ActionStep, FinalStep, step_grammar, step_model


def parse(registry: ToolRegistry, raw: str) -> ActionStep | FinalStep:
    return step_model(registry).model_validate_json(raw).root


def test_parses_a_final_answer(registry: ToolRegistry) -> None:
    step = parse(registry, final("5"))
    assert isinstance(step, FinalStep)
    assert step.final == "5"
    assert step.thought == "I know the answer."


def test_parses_a_tool_call_into_the_tools_own_args_model(registry: ToolRegistry) -> None:
    step = parse(registry, act("set_light", room="kitchen", on=True))
    assert isinstance(step, ActionStep)
    assert step.action.tool == "set_light"
    assert isinstance(step.action.args, LightArgs)
    assert step.action.args.room == "kitchen"


@pytest.mark.parametrize(
    "raw",
    [
        act("format_disk", drive="C"),  # not registered
        act("add", a=1),  # missing argument
        act("add", a=1, b=2, c=3),  # unknown argument
        act("add", a="one", b=2),  # wrong type
        act("set_light", room="", on=True),  # fails the args model's constraints
        json.dumps({"thought": "x"}),  # neither action nor final
        json.dumps({"thought": "x", "final": "y", "extra": 1}),
        json.dumps({"final": "y"}),  # no thought
        "not json",
    ],
)
def test_rejects_anything_that_is_not_a_valid_step(registry: ToolRegistry, raw: str) -> None:
    with pytest.raises(ValidationError):
        parse(registry, raw)


def test_the_model_is_rebuilt_when_tools_change(toolbox: Toolbox) -> None:
    registry = ToolRegistry([toolbox.add])
    with pytest.raises(ValidationError):
        parse(registry, act("set_light", room="hall", on=False))
    registry.register(toolbox.set_light)
    assert isinstance(parse(registry, act("set_light", room="hall", on=False)), ActionStep)


def test_an_empty_registry_only_allows_final_answers() -> None:
    registry = ToolRegistry()
    assert isinstance(parse(registry, final("hi")), FinalStep)
    with pytest.raises(ValidationError):
        parse(registry, act("add", a=1, b=2))


def test_grammar_lists_exactly_the_registered_tool_names(registry: ToolRegistry) -> None:
    grammar = step_grammar(registry)
    for name in registry.names():
        assert f'\\"{name}\\"' in grammar
    assert "format_disk" not in grammar


def test_grammar_puts_the_thought_first(registry: ToolRegistry) -> None:
    # Field order is generation order: the model reasons before it commits.
    rules = dict(
        line.split(" ::= ", 1) for line in step_grammar(registry).splitlines() if " ::= " in line
    )
    action, answer = rules["ActionStep"], rules["FinalStep"]
    assert action.index("thought") < action.index("action")
    assert answer.index("thought") < answer.index("final")


def test_grammar_is_accepted_by_llama_cpp(registry: ToolRegistry) -> None:
    LlamaGrammar.from_string(step_grammar(registry), verbose=False)


def test_two_tools_may_share_an_args_model(toolbox: Toolbox) -> None:
    # add and explode both take AddArgs.
    registry = ToolRegistry([toolbox.add, toolbox.explode])
    step = parse(registry, act("explode", a=1, b=2))
    assert isinstance(step, ActionStep)
    assert step.action.tool == "explode"
    assert isinstance(step.action.args, AddArgs)
    LlamaGrammar.from_string(step_grammar(registry), verbose=False)
