import pytest

from zeno.inference.base import ChatMessage
from zeno.memory.working import WorkingMemory


def u(text: str) -> ChatMessage:
    return ChatMessage("user", text)


def a(text: str) -> ChatMessage:
    return ChatMessage("assistant", text)


def test_starts_empty() -> None:
    memory = WorkingMemory(max_messages=4)
    assert memory.messages() == []
    assert memory.context == {}


def test_keeps_messages_in_order() -> None:
    memory = WorkingMemory(max_messages=4)
    memory.add(u("hi"))
    memory.add(a("hello"))
    assert memory.messages() == [u("hi"), a("hello")]


def test_evicts_the_oldest_messages_and_returns_them() -> None:
    memory = WorkingMemory(max_messages=3)
    assert memory.add(u("1")) == []
    memory.add(a("2"))
    memory.add(u("3"))
    assert memory.add(a("4")) == [u("1")]
    assert memory.messages() == [a("2"), u("3"), a("4")]


def test_messages_returns_a_copy() -> None:
    memory = WorkingMemory(max_messages=3)
    memory.add(u("1"))
    memory.messages().clear()
    assert len(memory.messages()) == 1


def test_session_context_can_be_set_replaced_and_removed() -> None:
    memory = WorkingMemory()
    memory.set_context("module", "weather")
    memory.set_context("module", "stocks")
    memory.set_context("form", "human")
    assert memory.context == {"module": "stocks", "form": "human"}
    memory.set_context("form", None)
    assert memory.context == {"module": "stocks"}


def test_clear_returns_everything_still_in_the_window() -> None:
    memory = WorkingMemory(max_messages=5)
    memory.add(u("1"))
    memory.add(a("2"))
    memory.set_context("module", "news")
    assert memory.clear() == [u("1"), a("2")]
    assert memory.messages() == []
    assert memory.context == {}


def test_rejects_a_window_smaller_than_one_exchange() -> None:
    with pytest.raises(ValueError):
        WorkingMemory(max_messages=1)
