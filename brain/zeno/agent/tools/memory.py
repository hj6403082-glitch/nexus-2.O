"""Long-term memory: recall what Zeno knows, remember new facts (with approval)."""

from typing import Any

from pydantic import Field

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool
from zeno.memory.manager import MemoryManager


class RecallArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=300, description="What to look for.")
    limit: int = Field(default=5, ge=1, le=10)


class FactArgs(ToolArgs):
    fact: str = Field(
        min_length=3, max_length=500, description="One lasting fact, as a full sentence."
    )


def memory_tools(memory: MemoryManager) -> list[Tool[Any]]:
    @tool(risk=Risk.READ_ONLY, timeout=10.0)
    async def recall_memory(args: RecallArgs) -> str:
        """Search long-term memory: facts about the owner and earlier conversations."""
        lines = await memory.recall(args.query, limit=args.limit)
        if not lines:
            return "Nothing relevant is remembered."
        return "\n".join(f"- {line}" for line in lines)

    @tool(risk=Risk.MUTATING, timeout=10.0)
    async def remember_fact(args: FactArgs) -> str:
        """Save a lasting fact about the owner or their preferences to long-term memory."""
        record = await memory.facts.remember(args.fact, source="agent")
        return f"Remembered: {record.text}"

    return [recall_memory, remember_fact]
