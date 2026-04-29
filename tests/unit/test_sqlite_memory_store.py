"""Tests for SQLiteMemoryStore."""

import threading
from pathlib import Path

import pytest

from src.memory.models import (
    MemoryEntry,
    MemoryEntryType,
    MergeMemory,
    PhaseSummary,
)
from src.memory.sqlite_store import SQLiteMemoryStore
from src.memory.store import MAX_ENTRIES


def _entry(content: str, phase: str = "planning", **kw) -> MemoryEntry:
    return MemoryEntry(
        entry_type=kw.pop("entry_type", MemoryEntryType.PATTERN),
        phase=phase,
        content=content,
        **kw,
    )


@pytest.fixture()
def store(tmp_path: Path) -> SQLiteMemoryStore:
    return SQLiteMemoryStore.open(tmp_path / "memory.db")


class TestOpen:
    def test_creates_db_file(self, tmp_path: Path) -> None:
        db = tmp_path / "new.db"
        assert not db.exists()
        SQLiteMemoryStore.open(db)
        assert db.exists()

    def test_open_existing_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "memory.db"
        s1 = SQLiteMemoryStore.open(db)
        s1.add_entry(_entry("hello"))
        s2 = SQLiteMemoryStore.open(db)
        assert s2.entry_count == 1


class TestAddEntry:
    def test_add_single(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("pattern A"))
        assert store.entry_count == 1

    def test_add_returns_self(self, store: SQLiteMemoryStore) -> None:
        result = store.add_entry(_entry("x"))
        assert result is store

    def test_dedup_by_content_hash(self, store: SQLiteMemoryStore) -> None:
        e = _entry("same content")
        store.add_entry(e)
        store.add_entry(e)
        assert store.entry_count == 1

    def test_eviction_at_max(self, tmp_path: Path) -> None:
        store = SQLiteMemoryStore.open(tmp_path / "big.db")
        for i in range(MAX_ENTRIES + 20):
            store.add_entry(
                _entry(f"unique content {i}", confidence=i / (MAX_ENTRIES + 20))
            )
        assert store.entry_count <= MAX_ENTRIES

    def test_eviction_keeps_highest_confidence(self, tmp_path: Path) -> None:
        store = SQLiteMemoryStore.open(tmp_path / "evict.db")
        store.add_entry(_entry("high confidence entry", confidence=0.99))
        for i in range(MAX_ENTRIES):
            store.add_entry(_entry(f"low {i}", confidence=0.01))
        results = store.query_by_type(MemoryEntryType.PATTERN, limit=MAX_ENTRIES)
        assert any("high confidence" in r.content for r in results)


class TestQueryByPath:
    def _populated(self, store: SQLiteMemoryStore) -> SQLiteMemoryStore:
        store.add_entry(
            _entry(
                "api model",
                file_paths=["api/models/user.py", "api/models/team.py"],
                tags=["api"],
            )
        )
        store.add_entry(
            _entry("vendor lib", file_paths=["vendor/lib.py"], tags=["vendor"])
        )
        return store

    def test_exact_path(self, store: SQLiteMemoryStore) -> None:
        self._populated(store)
        results = store.query_by_path("api/models/user.py")
        assert len(results) >= 1
        assert any("api" in r.content for r in results)

    def test_prefix_path(self, store: SQLiteMemoryStore) -> None:
        self._populated(store)
        results = store.query_by_path("api/models/")
        assert len(results) >= 1

    def test_no_match(self, store: SQLiteMemoryStore) -> None:
        self._populated(store)
        assert store.query_by_path("frontend/components/button.tsx") == []

    def test_limit_respected(self, store: SQLiteMemoryStore) -> None:
        for i in range(10):
            store.add_entry(_entry(f"p{i}", file_paths=["api/x.py"]))
        assert len(store.query_by_path("api/x.py", limit=3)) == 3


class TestQueryByTags:
    def test_matches_one_tag(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("A", tags=["alpha", "beta"]))
        store.add_entry(_entry("B", tags=["gamma"]))
        results = store.query_by_tags(["alpha"])
        assert len(results) == 1
        assert results[0].content == "A"

    def test_matches_any_tag(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("A", tags=["alpha"]))
        store.add_entry(_entry("B", tags=["beta"]))
        results = store.query_by_tags(["alpha", "beta"])
        assert len(results) == 2

    def test_no_match(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("A", tags=["alpha"]))
        assert store.query_by_tags(["gamma"]) == []


class TestQueryByType:
    def test_filters_by_type(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("P", entry_type=MemoryEntryType.PATTERN))
        store.add_entry(
            MemoryEntry(
                entry_type=MemoryEntryType.DECISION,
                phase="auto_merge",
                content="D",
            )
        )
        assert len(store.query_by_type(MemoryEntryType.PATTERN)) == 1
        assert len(store.query_by_type(MemoryEntryType.DECISION)) == 1

    def test_limit_zero(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("X"))
        assert store.query_by_type(MemoryEntryType.PATTERN, limit=0) == []


class TestPhaseSummary:
    def test_record_and_get(self, store: SQLiteMemoryStore) -> None:
        s = PhaseSummary(phase="planning", files_processed=42)
        store.record_phase_summary(s)
        result = store.get_phase_summary("planning")
        assert result is not None
        assert result.files_processed == 42

    def test_overwrite(self, store: SQLiteMemoryStore) -> None:
        store.record_phase_summary(PhaseSummary(phase="planning", files_processed=1))
        store.record_phase_summary(PhaseSummary(phase="planning", files_processed=99))
        assert store.get_phase_summary("planning").files_processed == 99  # type: ignore[union-attr]

    def test_missing_returns_none(self, store: SQLiteMemoryStore) -> None:
        assert store.get_phase_summary("nonexistent") is None


class TestCodebaseProfile:
    def test_set_and_read(self, store: SQLiteMemoryStore) -> None:
        store.set_codebase_profile("language", "python")
        assert store.codebase_profile["language"] == "python"

    def test_overwrite(self, store: SQLiteMemoryStore) -> None:
        store.set_codebase_profile("k", "v1")
        store.set_codebase_profile("k", "v2")
        assert store.codebase_profile["k"] == "v2"


class TestGetRelevantContext:
    def test_returns_matching_entries(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("api insight", file_paths=["api/models/x.py"]))
        store.add_entry(_entry("global insight"))
        results = store.get_relevant_context(["api/models/x.py"])
        contents = [r.content for r in results]
        assert "api insight" in contents

    def test_includes_global_entries(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("api insight", file_paths=["api/x.py"]))
        store.add_entry(_entry("global no path"))
        results = store.get_relevant_context(["api/x.py"], max_entries=10)
        contents = [r.content for r in results]
        assert "global no path" in contents

    def test_filters_by_min_relevance(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("api insight", file_paths=["api/x.py"], confidence=0.8))
        store.add_entry(_entry("unrelated insight", file_paths=["docs/y.md"]))

        results = store.get_relevant_context(
            ["api/x.py"], max_entries=10, min_relevance=0.9
        )

        assert [r.content for r in results] == ["api insight"]


class TestRemoveSuperseded:
    def test_removes_earlier_phase_entries(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("plan entry", phase="planning", file_paths=["a.py"]))
        store.add_entry(
            MemoryEntry(
                entry_type=MemoryEntryType.PATTERN,
                phase="auto_merge",
                content="merge entry",
                file_paths=["a.py"],
            )
        )
        before = store.entry_count
        store.remove_superseded("auto_merge")
        assert store.entry_count < before

    def test_does_nothing_for_planning(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("p", file_paths=["x.py"]))
        store.remove_superseded("planning")
        assert store.entry_count == 1

    def test_returns_self(self, store: SQLiteMemoryStore) -> None:
        assert store.remove_superseded("auto_merge") is store


class TestImportFromMemory:
    def test_roundtrip(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("original"))
        store.record_phase_summary(PhaseSummary(phase="planning", files_processed=5))
        store.set_codebase_profile("lang", "py")

        snapshot: MergeMemory = store.to_memory()

        store2 = SQLiteMemoryStore.open(store._db_path.parent / "store2.db")
        store2.import_from_memory(snapshot)

        assert store2.entry_count == 1
        assert store2.get_phase_summary("planning") is not None
        assert store2.codebase_profile["lang"] == "py"

    def test_import_no_duplicates(self, store: SQLiteMemoryStore) -> None:
        store.add_entry(_entry("dup"))
        snapshot = store.to_memory()
        store.import_from_memory(snapshot)
        assert store.entry_count == 1


class TestConcurrentWrites:
    def test_two_threads_no_error(self, tmp_path: Path) -> None:
        db = tmp_path / "concurrent.db"
        errors: list[Exception] = []

        def write(n: int) -> None:
            s = SQLiteMemoryStore.open(db)
            for i in range(10):
                try:
                    s.add_entry(_entry(f"thread{n} item{i} unique_{n}_{i}"))
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=write, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent writes raised: {errors}"
        final = SQLiteMemoryStore.open(db)
        assert final.entry_count == 40
