"""speak_answers: the ReAct answer becomes SpeechSynthesisRequested events, one per
sentence; every agent event still passes through unchanged."""

from collections.abc import AsyncGenerator, Sequence

import pytest

from zeno.agent.events import AgentEvent, Finished, Observation, Thought
from zeno.multimodal.speech import speak_answers, speakable, split_sentences
from zeno.senses.events import DeviceEvent
from zeno.senses.protocol import SpeechSynthesisRequested


async def stream(events: Sequence[AgentEvent]) -> AsyncGenerator[AgentEvent, None]:
    for event in events:
        yield event


def spoken(published: list[DeviceEvent]) -> list[str]:
    return [SpeechSynthesisRequested.from_event(e).text for e in published]


def test_sentences_are_split() -> None:
    assert split_sentences("It is 9 pm. The sky is clear! Want more?") == [
        "It is 9 pm.",
        "The sky is clear!",
        "Want more?",
    ]


def test_lines_split_and_blank_text_vanishes() -> None:
    assert split_sentences("First line\nSecond line") == ["First line", "Second line"]
    assert split_sentences("   ") == []


def test_long_sentences_are_cut_at_word_boundaries() -> None:
    parts = split_sentences("word " * 400, max_chars=100)
    assert all(0 < len(p) <= 100 for p in parts)
    assert " ".join(parts).split() == ["word"] * 400


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("**Bold** and _soft_ and `code`.", "Bold and soft and code."),
        ("# Heading\n- item one", "Heading\nitem one"),
        ("See [the docs](https://example.com/x).", "See the docs."),
        ("Go to https://example.com/very/long now.", "Go to the link in the chat now."),
        ("Run this:\n```python\nprint(1)\n```\nDone.", "Run this:\nthe code in the chat\nDone."),
    ],
)
def test_markdown_is_made_speakable(text: str, expected: str) -> None:
    assert speakable(text) == expected


async def test_events_pass_through_and_the_answer_is_spoken() -> None:
    published: list[DeviceEvent] = []
    events: list[AgentEvent] = [
        Thought(1, "I should check the clock."),
        Observation(1, "get_time", True, "21:00"),
        Finished("answered", "It is 9 pm. Anything else?", 2),
    ]
    out = [e async for e in speak_answers(stream(events), published.append, turn_id="t1")]
    assert out == events
    assert spoken(published) == ["It is 9 pm.", "Anything else?"]
    assert all(SpeechSynthesisRequested.from_event(e).turn_id == "t1" for e in published)


async def test_thoughts_and_observations_are_never_spoken() -> None:
    published: list[DeviceEvent] = []
    events: list[AgentEvent] = [Thought(1, "secret plan"), Observation(1, "x", True, "data")]
    _ = [e async for e in speak_answers(stream(events), published.append)]
    assert published == []


async def test_failed_runs_still_say_their_friendly_message() -> None:
    published: list[DeviceEvent] = []
    events: list[AgentEvent] = [Finished("step_limit", "I couldn't finish that.", 5)]
    _ = [e async for e in speak_answers(stream(events), published.append)]
    assert spoken(published) == ["I couldn't finish that."]


async def test_closing_early_closes_the_inner_stream() -> None:
    closed = False

    async def inner() -> AsyncGenerator[AgentEvent, None]:
        nonlocal closed
        try:
            yield Thought(1, "one")
            yield Thought(2, "two")
        finally:
            closed = True

    wrapped = speak_answers(inner(), lambda _: None)
    assert isinstance(await anext(wrapped), Thought)
    await wrapped.aclose()
    assert closed
