"""Tests for content_hash field and MemoryStore deduplication."""

from src.memory.models import (
    MemoryEntry,
    MemoryEntryType,
)
from src.memory.store import MemoryStore


class TestContentHash:
    def test_content_hash_generated(self):
        entry = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="vendor/ is mostly B-class",
        )
        assert len(entry.content_hash) == 16
        assert entry.content_hash != ""

    def test_same_content_same_hash(self):
        e1 = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="vendor/ is mostly B-class",
        )
        e2 = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="vendor/ is mostly B-class",
        )
        assert e1.content_hash == e2.content_hash

    def test_different_content_different_hash(self):
        e1 = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="pattern A",
        )
        e2 = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="pattern B",
        )
        assert e1.content_hash != e2.content_hash

    def test_different_phase_different_hash(self):
        e1 = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="vendor/ is mostly B-class",
        )
        e2 = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="auto_merge",
            content="vendor/ is mostly B-class",
        )
        assert e1.content_hash != e2.content_hash

    def test_different_type_different_hash(self):
        e1 = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="same content",
        )
        e2 = MemoryEntry(
            entry_type=MemoryEntryType.DECISION,
            phase="planning",
            content="same content",
        )
        assert e1.content_hash != e2.content_hash

    def test_hash_survives_serialization(self):
        entry = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="test pattern",
        )
        original_hash = entry.content_hash
        data = entry.model_dump(mode="json")
        restored = MemoryEntry.model_validate(data)
        assert restored.content_hash == original_hash


class TestMemoryStoreDedup:
    def test_dedup_skips_duplicate(self):
        entry = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="same content",
        )
        store = MemoryStore()
        store = store.add_entry(entry)
        store = store.add_entry(entry)
        assert store.entry_count == 1

    def test_dedup_keeps_different_entries(self):
        e1 = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="pattern A",
        )
        e2 = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="pattern B",
        )
        store = MemoryStore()
        store = store.add_entry(e1)
        store = store.add_entry(e2)
        assert store.entry_count == 2

    def test_dedup_same_content_different_phase_kept(self):
        e1 = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="shared pattern",
        )
        e2 = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="auto_merge",
            content="shared pattern",
        )
        store = MemoryStore()
        store = store.add_entry(e1)
        store = store.add_entry(e2)
        assert store.entry_count == 2

    def test_dedup_returns_self_on_duplicate(self):
        entry = MemoryEntry(
            entry_type=MemoryEntryType.PATTERN,
            phase="planning",
            content="test",
        )
        store = MemoryStore()
        store1 = store.add_entry(entry)
        store2 = store1.add_entry(entry)
        assert store2 is store1
