import pytest

from zeno.inference.think_filter import ThinkFilter


def run(chunks: list[str]) -> str:
    f = ThinkFilter()
    return "".join(f.push(c) for c in chunks) + f.flush()


def test_passes_plain_text_through() -> None:
    assert run(["Hello ", "there"]) == "Hello there"


def test_strips_a_think_block() -> None:
    assert run(["<think>plan it</think>Answer"]) == "Answer"


@pytest.mark.parametrize("split", range(1, 30))
def test_strips_tags_split_at_any_boundary(split: int) -> None:
    text = "Hi <think>secret plan</think>there"
    assert run([text[:split], text[split:]]) == "Hi there"


def test_character_by_character() -> None:
    assert run(list("a<think>x</think>b<think>y</think>c")) == "abc"


def test_holds_back_partial_tag_until_resolved() -> None:
    f = ThinkFilter()
    assert f.push("value <th") == "value "
    assert f.push("ree") == "<three"


def test_flush_releases_trailing_partial_tag() -> None:
    f = ThinkFilter()
    assert f.push("a <thi") == "a "
    assert f.flush() == "<thi"


def test_flush_drops_unterminated_think_block() -> None:
    f = ThinkFilter()
    assert f.push("ok<think>never closed") == "ok"
    assert f.flush() == ""
