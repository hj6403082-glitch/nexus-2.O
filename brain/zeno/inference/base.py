"""Inference contracts shared by every engine and by the rest of the brain."""

from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class GenerationParams:
    max_tokens: int = 700
    temperature: float = 0.7
    top_p: float = 0.95
    stop: tuple[str, ...] = ()
    seed: int | None = None
    grammar: str | None = None
    """GBNF grammar the output must match (see zeno.inference.grammar)."""


class InferenceEngine(Protocol):
    """Anything that can turn a chat into streamed text."""

    @property
    def context_size(self) -> int: ...

    def count_tokens(self, text: str) -> int: ...

    def stream(
        self, messages: Sequence[ChatMessage], params: GenerationParams | None = None
    ) -> AsyncGenerator[str, None]:
        """Yield text chunks. Close the generator (``contextlib.aclosing``) to stop early."""
        ...


class InferenceError(Exception):
    """Base class for every inference failure."""


class ModelNotFoundError(InferenceError):
    pass


class ModelLoadError(InferenceError):
    pass


class EngineBusyError(InferenceError):
    pass


class GrammarError(InferenceError):
    pass


class PromptTooLongError(InferenceError):
    pass


class StructuredOutputError(InferenceError):
    def __init__(self, message: str, raw: str) -> None:
        super().__init__(message)
        self.raw = raw
