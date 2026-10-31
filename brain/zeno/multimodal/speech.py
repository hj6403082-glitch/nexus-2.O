"""ReAct output to speech: turn a run's answer into SpeechSynthesisRequested events.

The agent's steps are grammar-constrained JSON, so there is no token stream worth
speaking; the answer arrives whole in ``Finished``. ``speak_answers`` wraps any event
stream, passes every event through unchanged, and publishes the answer one sentence
at a time, so the first sentence plays while the next is being synthesised.
"""

import re
from collections.abc import AsyncGenerator, Callable
from contextlib import aclosing

from zeno.agent.events import AgentEvent, Finished
from zeno.senses.events import DeviceEvent
from zeno.senses.protocol import SpeechSynthesisRequested

Publish = Callable[[DeviceEvent], None]

MAX_SPOKEN_CHARS = 1000  # SpeechSynthesisRequested.text's limit

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL = re.compile(r"https?://\S+?(?=[.,;:!?)]*(?:\s|$))")
_HEADING_OR_BULLET = re.compile(r"^\s*(?:#{1,6}\s+|[-*+]\s+|>\s*|\d+[.)]\s+)", re.MULTILINE)
_EMPHASIS = re.compile(r"(\*\*|__|\*|_|`)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def speakable(text: str) -> str:
    """Strip markdown and swap code and URLs for a pointer to the chat."""
    text = _CODE_BLOCK.sub("the code in the chat", text)
    text = _LINK.sub(r"\1", text)
    text = _URL.sub("the link in the chat", text)
    text = _HEADING_OR_BULLET.sub("", text)
    text = _EMPHASIS.sub("", text)
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def split_sentences(text: str, *, max_chars: int = MAX_SPOKEN_CHARS) -> list[str]:
    """Sentences (and lines) in order, none longer than ``max_chars``."""
    out: list[str] = []
    for line in text.splitlines():
        for sentence in _SENTENCE_END.split(line.strip()):
            sentence = sentence.strip()
            if sentence:
                out.extend(_cut(sentence, max_chars))
    return out


def _cut(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    parts: list[str] = []
    current = ""
    for word in sentence.split():
        word = word[:max_chars]
        if current and len(current) + 1 + len(word) > max_chars:
            parts.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        parts.append(current)
    return parts


def say(publish: Publish, text: str, *, turn_id: str | None = None) -> int:
    """Publish ``text`` as speech requests, one per sentence. Returns how many."""
    sentences = split_sentences(speakable(text))
    for sentence in sentences:
        publish(SpeechSynthesisRequested(text=sentence, turn_id=turn_id).to_event())
    return len(sentences)


async def speak_answers(
    events: AsyncGenerator[AgentEvent, None], publish: Publish, *, turn_id: str | None = None
) -> AsyncGenerator[AgentEvent, None]:
    """Yield ``events`` unchanged; speak the run's final message when it arrives.

    Thoughts, tool calls and observations are never spoken. A run that ends without
    an answer (step limit, error) still says its short, friendly message."""
    async with aclosing(events) as stream:
        async for event in stream:
            if isinstance(event, Finished) and event.answer:
                say(publish, event.answer, turn_id=turn_id)
            yield event
