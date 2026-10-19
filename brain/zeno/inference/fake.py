"""A scripted engine for tests of anything that consumes an InferenceEngine."""

from collections.abc import AsyncGenerator, Sequence

from zeno.inference.base import ChatMessage, GenerationParams, InferenceError


class ScriptedEngine:
    """Replays one scripted response per ``stream`` call and records each call.

    A response is a string (one chunk) or a list of chunks.
    """

    def __init__(self, responses: Sequence[str | Sequence[str]], *, context_size: int = 4096):
        self._responses = [[r] if isinstance(r, str) else list(r) for r in responses]
        self._context_size = context_size
        self.calls: list[tuple[list[ChatMessage], GenerationParams]] = []

    async def load(self) -> None:
        """Nothing to load; mirrors ``LlamaCppEngine.load``."""

    def close(self) -> None:
        """Nothing to free; mirrors ``LlamaCppEngine.close``."""

    @property
    def context_size(self) -> int:
        return self._context_size

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    async def stream(
        self, messages: Sequence[ChatMessage], params: GenerationParams | None = None
    ) -> AsyncGenerator[str, None]:
        self.calls.append((list(messages), params or GenerationParams()))
        if not self._responses:
            raise InferenceError("ScriptedEngine has no responses left")
        for chunk in self._responses.pop(0):
            yield chunk
