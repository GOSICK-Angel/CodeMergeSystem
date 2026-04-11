"""Tests for BaseAgent.get_memory_context() layered loading integration."""

from unittest.mock import patch

from src.memory.models import (
    ConfidenceLevel,
    MemoryEntry,
    MemoryEntryType,
    PhaseSummary,
)
from src.memory.store import MemoryStore
from src.models.config import AgentLLMConfig


def _make_concrete_agent():
    """Create a minimal concrete agent for testing base class methods."""
    from src.agents.base_agent import BaseAgent
    from src.models.message import AgentType, AgentMessage
    from src.models.state import MergeState

    class StubAgent(BaseAgent):
        agent_type = AgentType.PLANNER

        async def run(self, state):
            return AgentMessage(
                sender=self.agent_type,
                content="stub",
            )

        def can_handle(self, state: MergeState) -> bool:
            return True

    config = AgentLLMConfig(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
    )
    with patch("src.llm.client.LLMClientFactory.create"):
        return StubAgent(config)


class TestGetMemoryContext:
    def test_returns_empty_without_store(self):
        agent = _make_concrete_agent()
        result = agent.get_memory_context("planning")
        assert result == ""

    def test_returns_layered_context_with_store(self):
        agent = _make_concrete_agent()
        store = MemoryStore()
        store = store.set_codebase_profile("language", "python")
        store = store.add_entry(
            MemoryEntry(
                entry_type=MemoryEntryType.PATTERN,
                phase="planning",
                content="relevant pattern",
                file_paths=["src/core/engine.py"],
                confidence_level=ConfidenceLevel.EXTRACTED,
            )
        )
        agent.set_memory_store(store)

        result = agent.get_memory_context(
            "auto_merge", file_paths=["src/core/engine.py"]
        )
        assert "python" in result
        assert "relevant pattern" in result
        assert "EXTRACTED" in result

    def test_without_file_paths_no_l2(self):
        agent = _make_concrete_agent()
        store = MemoryStore()
        store = store.set_codebase_profile("language", "go")
        store = store.add_entry(
            MemoryEntry(
                entry_type=MemoryEntryType.PATTERN,
                phase="planning",
                content="file-specific only",
                file_paths=["src/handler.go"],
            )
        )
        agent.set_memory_store(store)

        result = agent.get_memory_context("planning")
        assert "go" in result
        assert "file-specific only" not in result
