import pytest

from zeno.inference.base import ChatMessage, PromptTooLongError
from zeno.inference.prompt import PromptBuilder

SYSTEM = "You are Zeno."


def words(text: str) -> int:
    return len(text.split())


def builder(context_size: int = 1000, reserve: int = 0, overhead: int = 0) -> PromptBuilder:
    return PromptBuilder(
        SYSTEM,
        count_tokens=words,
        context_size=context_size,
        reserve_tokens=reserve,
        message_overhead=overhead,
    )


def user(text: str) -> ChatMessage:
    return ChatMessage("user", text)


def assistant(text: str) -> ChatMessage:
    return ChatMessage("assistant", text)


def test_system_prompt_comes_first_and_is_byte_stable() -> None:
    b = builder()
    first = b.build([user("hi")], context="weather: sunny")
    second = b.build([user("hi"), assistant("hello"), user("again")], context="stocks: up")
    assert first[0] == ChatMessage("system", SYSTEM)
    assert second[0] == first[0]


def test_context_and_memories_ride_on_the_last_user_message_only() -> None:
    history = [user("first question"), assistant("first answer"), user("what now?")]
    built = builder().build(
        history, context="module: weather", memories=["likes green", "lives here"]
    )
    assert built[1:3] == history[:2]
    last = built[-1]
    assert last.role == "user"
    assert last.content.endswith("what now?")
    for piece in ("module: weather", "likes green", "lives here", "not instructions"):
        assert piece in last.content


def test_without_context_the_last_message_is_unchanged() -> None:
    history = [user("plain")]
    assert builder().build(history)[-1] == history[-1]


def test_trims_oldest_history_to_fit_the_budget() -> None:
    history = [user("one two three"), assistant("four five six"), user("seven eight")]
    # system (3 words) + last (2) fits in 6; the older pair does not.
    built = builder(context_size=10, reserve=4).build(history)
    assert built == [ChatMessage("system", SYSTEM), user("seven eight")]


def test_counts_per_message_overhead() -> None:
    history = [user("a"), assistant("b"), user("c")]
    roomy = builder(context_size=100, overhead=4).build(history)
    tight = builder(context_size=12, overhead=4).build(history)
    assert len(roomy) == 4
    assert tight == [ChatMessage("system", SYSTEM), user("c")]


def test_history_never_starts_with_an_assistant_turn_after_trimming() -> None:
    history = [user("x " * 5), assistant("short"), user("last")]
    built = builder(context_size=6).build(history)
    assert [m.role for m in built] == ["system", "user"]


def test_drops_least_relevant_memories_before_giving_up() -> None:
    long_memory = "word " * 50
    built = builder(context_size=40).build([user("hello")], memories=["short fact", long_memory])
    assert "short fact" in built[-1].content
    assert long_memory.strip() not in built[-1].content


def test_raises_when_the_newest_message_cannot_fit() -> None:
    with pytest.raises(PromptTooLongError):
        builder(context_size=10).build([user("word " * 20)])


def test_reserve_tokens_are_kept_free_for_the_answer() -> None:
    with pytest.raises(PromptTooLongError):
        builder(context_size=10, reserve=8).build([user("one two three four")])


@pytest.mark.parametrize("history", [[], [assistant("hi")]])
def test_requires_a_final_user_message(history: list[ChatMessage]) -> None:
    with pytest.raises(ValueError):
        builder().build(history)
