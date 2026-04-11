"""Tests for ConfidenceLevel enum and MemoryEntry.confidence_level field."""

import pytest

from src.memory.models import (
    ConfidenceLevel,
    MemoryEntry,
    MemoryEntryType,
)


class TestConfidenceLevel:
    def test_enum_values(self):
        assert ConfidenceLevel.EXTRACTED == "extracted"
        assert ConfidenceLevel.INFERRED == "inferred"
        assert ConfidenceLevel.HEURISTIC == "heuristic"

    def test_enum_is_str(self):
        assert isinstance(ConfidenceLevel.EXTRACTED, str)


class TestMemoryEntryConfidenceLevel:
    def test_default_confidence_level(self):
        entry = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="test",
        )
        assert entry.confidence_level == ConfidenceLevel.INFERRED

    def test_explicit_confidence_level(self):
        entry = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="test",
            confidence_level=ConfidenceLevel.EXTRACTED,
        )
        assert entry.confidence_level == ConfidenceLevel.EXTRACTED
        assert entry.confidence == 0.8

    def test_heuristic_level(self):
        entry = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="judge_review",
            content="test",
            confidence_level=ConfidenceLevel.HEURISTIC,
        )
        assert entry.confidence_level == ConfidenceLevel.HEURISTIC

    def test_backward_compatible_deserialization(self):
        old_json = {
            "entry_id": "abc-123",
            "entry_type": "pattern",
            "phase": "planning",
            "content": "test",
            "confidence": 0.9,
            "file_paths": [],
            "tags": [],
        }
        entry = MemoryEntry.model_validate(old_json)
        assert entry.confidence_level == ConfidenceLevel.INFERRED
        assert entry.confidence == 0.9

    def test_serialization_roundtrip_with_confidence_level(self):
        entry = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="test pattern",
            confidence_level=ConfidenceLevel.EXTRACTED,
        )
        data = entry.model_dump(mode="json")
        restored = MemoryEntry.model_validate(data)
        assert restored.confidence_level == ConfidenceLevel.EXTRACTED

    def test_frozen_confidence_level(self):
        entry = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="test",
        )
        with pytest.raises(Exception):
            entry.confidence_level = ConfidenceLevel.EXTRACTED
