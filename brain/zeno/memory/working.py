"""Working memory: the live conversation window and session context, held in RAM."""

from collections import deque

from zeno.inference.base import ChatMessage


class WorkingMemory:
    def __init__(self, max_messages: int = 20) -> None:
        if max_messages < 2:
            raise ValueError("the window must hold at least one exchange (2 messages)")
        self._messages: deque[ChatMessage] = deque()
        self._max = max_messages
        self._context: dict[str, str] = {}

    def add(self, message: ChatMessage) -> list[ChatMessage]:
        """Append a message; return any that fell out of the window (to archive)."""
        self._messages.append(message)
        evicted = []
        while len(self._messages) > self._max:
            evicted.append(self._messages.popleft())
        return evicted

    def messages(self) -> list[ChatMessage]:
        return list(self._messages)

    @property
    def context(self) -> dict[str, str]:
        return dict(self._context)

    def set_context(self, key: str, value: str | None) -> None:
        if value is None:
            self._context.pop(key, None)
        else:
            self._context[key] = value

    def clear(self) -> list[ChatMessage]:
        """End the session; return the messages still in the window."""
        remaining = list(self._messages)
        self._messages.clear()
        self._context.clear()
        return remaining
