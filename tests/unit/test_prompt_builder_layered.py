"""Tests for AgentPromptBuilder layered memory integration."""

from src.llm.prompt_builders import AgentPromptBuilder
from src.memory.models import (
    ConfidenceLevel,
    MemoryEntry,
    MemoryEntryType,
    PhaseSummary,
)
from src.memory.store import MemoryStore
from src.models.config import AgentLLMConfig


def _make_config() -> AgentLLMConfig:
    return AgentLLMConfig(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
    )


class TestBuildMemoryContextTextLayered:
    def test_includes_profile_as_l0(self):
        store = MemoryStore()
        store = store.set_codebase_profile("language", "python")

        builder = AgentPromptBuilder(_make_config(), store)
        result = builder.build_memory_context_text(
            file_paths=["src/main.py"],
            current_phase="planning",
        )

        assert "python" in result

    def test_includes_phase_summary_as_l1(self):
        store = MemoryStore()
        store = store.record_phase_summary(
            PhaseSummary(
                phase="planning",
                key_decisions=["Plan with 5 batches"],
            )
        )

        builder = AgentPromptBuilder(_make_config(), store)
        result = builder.build_memory_context_text(
            file_paths=["src/main.py"],
            current_phase="auto_merge",
        )

        assert "5 batches" in result

    def test_includes_file_relevant_as_l2(self):
        store = MemoryStore()
        store = store.add_entry(
            MemoryEntry(
                entry_type=MemoryEntryType.PATTERN,
                phase="planning",
                content="auth conflict pattern",
                file_paths=["src/auth/handler.py"],
                confidence_level=ConfidenceLevel.EXTRACTED,
            )
        )

        builder = AgentPromptBuilder(_make_config(), store)
        result = builder.build_memory_context_text(
            file_paths=["src/auth/handler.py"],
            current_phase="auto_merge",
        )

        assert "auth conflict" in result
        assert "EXTRACTED" in result

    def test_excludes_unrelated_files(self):
        store = MemoryStore()
        store = store.add_entry(
            MemoryEntry(
                entry_type=MemoryEntryType.PATTERN,
                phase="planning",
                content="vendor secret pattern",
                file_paths=["vendor/lib.py"],
            )
        )

        builder = AgentPromptBuilder(_make_config(), store)
        result = builder.build_memory_context_text(
            file_paths=["src/auth/handler.py"],
            current_phase="auto_merge",
        )

        assert "vendor secret" not in result

    def test_empty_store_returns_empty(self):
        store = MemoryStore()
        builder = AgentPromptBuilder(_make_config(), store)
        result = builder.build_memory_context_text(
            file_paths=["foo.py"],
            current_phase="planning",
        )
        assert result == ""

    def test_no_store_returns_empty(self):
        builder = AgentPromptBuilder(_make_config(), None)
        result = builder.build_memory_context_text(
            file_paths=["foo.py"],
            current_phase="planning",
        )
        assert result == ""

    def test_backward_compat_no_phase_arg(self):
        """Old call sites without current_phase should still work."""
        store = MemoryStore()
        store = store.add_entry(
            MemoryEntry(
                entry_type=MemoryEntryType.PATTERN,
                phase="planning",
                content="backward compat pattern",
                file_paths=["src/main.py"],
            )
        )

        builder = AgentPromptBuilder(_make_config(), store)
        result = builder.build_memory_context_text(file_paths=["src/main.py"])
        assert "backward compat" in result
