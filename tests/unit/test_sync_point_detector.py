"""Tests for SyncPointDetector — migration-aware merge-base detection."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.tools.sync_point_detector import SyncPointDetector, SyncPointResult


def _mock_git_tool(
    base_hashes: dict[str, str],
    fork_hashes: dict[str, str],
    up_hashes: dict[str, str],
    commits: list[dict] | None = None,
) -> MagicMock:
    git = MagicMock()

    def _list_files_with_hashes(ref: str) -> dict[str, str]:
        mapping = {
            "base_sha": base_hashes,
            "fork_ref": fork_hashes,
            "upstream_ref": up_hashes,
        }
        return mapping.get(ref, {})

    git.list_files_with_hashes.side_effect = _list_files_with_hashes
    git.list_commits.return_value = commits or []
    git.get_diff_patch_id.return_value = None
    return git


class TestSyncPointResult:
    def test_default_values(self):
        result = SyncPointResult()
        assert result.detected is False
        assert result.effective_merge_base == ""
        assert result.confidence == 0.0
        assert result.patch_id_promoted_count == 0

    def test_serialization_roundtrip(self):
        result = SyncPointResult(
            detected=True,
            effective_merge_base="abc123",
            git_merge_base="def456",
            synced_file_count=10,
            upstream_changed_file_count=20,
            sync_ratio=0.5,
            confidence=0.8,
            patch_id_promoted_count=2,
        )
        data = result.model_dump()
        restored = SyncPointResult.model_validate(data)
        assert restored == result


class TestFileLevelDetection:
    def test_no_upstream_changes(self):
        base = {"a.py": "h1", "b.py": "h2"}
        fork = {"a.py": "h1", "b.py": "h2"}
        up = {"a.py": "h1", "b.py": "h2"}
        synced, changed, ambiguous = SyncPointDetector._file_level_detection(
            base, fork, up
        )
        assert len(changed) == 0
        assert len(synced) == 0
        assert len(ambiguous) == 0

    def test_all_synced(self):
        base = {"a.py": "h1", "b.py": "h2"}
        fork = {"a.py": "h3", "b.py": "h4"}
        up = {"a.py": "h3", "b.py": "h4"}
        synced, changed, ambiguous = SyncPointDetector._file_level_detection(
            base, fork, up
        )
        assert changed == {"a.py", "b.py"}
        assert synced == {"a.py", "b.py"}
        assert len(ambiguous) == 0

    def test_none_synced(self):
        base = {"a.py": "h1", "b.py": "h2"}
        fork = {"a.py": "h1", "b.py": "h2"}
        up = {"a.py": "h3", "b.py": "h4"}
        synced, changed, ambiguous = SyncPointDetector._file_level_detection(
            base, fork, up
        )
        assert changed == {"a.py", "b.py"}
        assert len(synced) == 0
        assert len(ambiguous) == 0

    def test_partial_sync(self):
        base = {"a.py": "h1", "b.py": "h2", "c.py": "h3"}
        fork = {"a.py": "h4", "b.py": "h2", "c.py": "h5"}
        up = {"a.py": "h4", "b.py": "h5", "c.py": "h6"}
        synced, changed, ambiguous = SyncPointDetector._file_level_detection(
            base, fork, up
        )
        assert changed == {"a.py", "b.py", "c.py"}
        assert synced == {"a.py"}
        assert "c.py" in ambiguous

    def test_new_upstream_file_synced(self):
        base = {"a.py": "h1"}
        fork = {"a.py": "h1", "new.py": "h_new"}
        up = {"a.py": "h1", "new.py": "h_new"}
        synced, changed, ambiguous = SyncPointDetector._file_level_detection(
            base, fork, up
        )
        assert "new.py" in changed
        assert "new.py" in synced

    def test_new_upstream_file_not_synced(self):
        base = {"a.py": "h1"}
        fork = {"a.py": "h1"}
        up = {"a.py": "h1", "new.py": "h_new"}
        synced, changed, ambiguous = SyncPointDetector._file_level_detection(
            base, fork, up
        )
        assert "new.py" in changed
        assert "new.py" not in synced

    def test_ambiguous_detected(self):
        base = {"a.py": "h1", "b.py": "h2"}
        fork = {"a.py": "h_fork", "b.py": "h_fork2"}
        up = {"a.py": "h_up", "b.py": "h_up2"}
        synced, changed, ambiguous = SyncPointDetector._file_level_detection(
            base, fork, up
        )
        assert changed == {"a.py", "b.py"}
        assert len(synced) == 0
        assert ambiguous == {"a.py", "b.py"}


class TestPatchIdVerification:
    def test_patch_id_promotes_matching_files(self):
        git = MagicMock()

        def _fake_patch_id(base, ref, fp):
            if fp == "a.py":
                return "same_pid"
            return f"pid_{ref}_{fp}"

        git.get_diff_patch_id.side_effect = _fake_patch_id

        ambiguous = {"a.py", "b.py"}
        promoted = SyncPointDetector._patch_id_verification(
            git, "base", "fork", "up", ambiguous
        )
        assert "a.py" in promoted
        assert "b.py" not in promoted

    def test_patch_id_no_matches(self):
        git = MagicMock()
        git.get_diff_patch_id.side_effect = lambda b, r, f: f"pid_{r}_{f}"

        promoted = SyncPointDetector._patch_id_verification(
            git, "base", "fork", "up", {"a.py"}
        )
        assert len(promoted) == 0

    def test_patch_id_handles_none(self):
        git = MagicMock()
        git.get_diff_patch_id.return_value = None

        promoted = SyncPointDetector._patch_id_verification(
            git, "base", "fork", "up", {"a.py"}
        )
        assert len(promoted) == 0

    def test_patch_id_handles_exception(self):
        git = MagicMock()
        git.get_diff_patch_id.side_effect = Exception("git error")

        promoted = SyncPointDetector._patch_id_verification(
            git, "base", "fork", "up", {"a.py"}
        )
        assert len(promoted) == 0

    def test_detect_with_patch_id_promotion(self):
        base = {f"f{i}.py": f"base_{i}" for i in range(10)}
        fork_hashes = {}
        up_hashes = {}
        for i in range(10):
            if i < 4:
                fork_hashes[f"f{i}.py"] = f"up_{i}"
                up_hashes[f"f{i}.py"] = f"up_{i}"
            elif i < 7:
                fork_hashes[f"f{i}.py"] = f"fork_{i}"
                up_hashes[f"f{i}.py"] = f"up_{i}"
            else:
                fork_hashes[f"f{i}.py"] = f"base_{i}"
                up_hashes[f"f{i}.py"] = f"up_{i}"

        git = _mock_git_tool(base, fork_hashes, up_hashes)

        def _fake_patch_id(b, r, fp):
            if fp in ("f4.py", "f5.py"):
                return "same_pid"
            return f"pid_{r}_{fp}"

        git.get_diff_patch_id.side_effect = _fake_patch_id

        detector = SyncPointDetector(
            sync_ratio_threshold=0.3, min_synced_files=5, enable_patch_id=True
        )
        result = detector.detect(git, "base_sha", "fork_ref", "upstream_ref")

        assert result.detected is True
        assert result.patch_id_promoted_count == 2
        assert result.synced_file_count == 6

    def test_detect_without_patch_id(self):
        base = {f"f{i}.py": f"base_{i}" for i in range(10)}
        fork_hashes = {}
        up_hashes = {}
        for i in range(10):
            if i < 4:
                fork_hashes[f"f{i}.py"] = f"up_{i}"
                up_hashes[f"f{i}.py"] = f"up_{i}"
            else:
                fork_hashes[f"f{i}.py"] = f"fork_{i}"
                up_hashes[f"f{i}.py"] = f"up_{i}"

        git = _mock_git_tool(base, fork_hashes, up_hashes)

        detector = SyncPointDetector(
            sync_ratio_threshold=0.3, min_synced_files=5, enable_patch_id=False
        )
        result = detector.detect(git, "base_sha", "fork_ref", "upstream_ref")

        assert result.patch_id_promoted_count == 0
        assert result.synced_file_count == 4


class TestDetect:
    def test_no_migration_when_nothing_synced(self):
        git = _mock_git_tool(
            base_hashes={"a.py": "h1", "b.py": "h2"},
            fork_hashes={"a.py": "h1", "b.py": "h2"},
            up_hashes={"a.py": "h3", "b.py": "h4"},
        )
        detector = SyncPointDetector(
            sync_ratio_threshold=0.3, min_synced_files=2, enable_patch_id=False
        )
        result = detector.detect(git, "base_sha", "fork_ref", "upstream_ref")
        assert result.detected is False
        assert result.effective_merge_base == "base_sha"

    def test_no_migration_below_min_files(self):
        git = _mock_git_tool(
            base_hashes={"a.py": "h1"},
            fork_hashes={"a.py": "h3"},
            up_hashes={"a.py": "h3"},
        )
        detector = SyncPointDetector(
            sync_ratio_threshold=0.3, min_synced_files=5, enable_patch_id=False
        )
        result = detector.detect(git, "base_sha", "fork_ref", "upstream_ref")
        assert result.detected is False
        assert result.sync_ratio == 1.0
        assert result.synced_file_count == 1

    def test_migration_detected_with_commits(self):
        base = {f"f{i}.py": f"base_{i}" for i in range(10)}
        fork = {f"f{i}.py": f"up_{i}" for i in range(10)}
        up = {f"f{i}.py": f"up_{i}" for i in range(10)}

        commits = [
            {
                "sha": f"c{i}",
                "files": [f"f{i}.py"],
                "message": f"commit {i}",
                "date": "2025-01-01",
            }
            for i in range(10)
        ]

        git = _mock_git_tool(base, fork, up, commits)
        detector = SyncPointDetector(
            sync_ratio_threshold=0.3, min_synced_files=5, enable_patch_id=False
        )
        result = detector.detect(git, "base_sha", "fork_ref", "upstream_ref")

        assert result.detected is True
        assert result.sync_ratio == 1.0
        assert result.synced_file_count == 10
        assert result.effective_merge_base == "c9"
        assert result.skipped_commit_count == 10
        assert result.confidence > 0

    def test_partial_migration_boundary(self):
        base = {f"f{i}.py": f"base_{i}" for i in range(10)}
        fork_hashes = {}
        up_hashes = {}
        for i in range(10):
            if i < 6:
                fork_hashes[f"f{i}.py"] = f"up_{i}"
                up_hashes[f"f{i}.py"] = f"up_{i}"
            else:
                fork_hashes[f"f{i}.py"] = f"base_{i}"
                up_hashes[f"f{i}.py"] = f"up_{i}"

        commits = [
            {
                "sha": f"c{i}",
                "files": [f"f{i}.py"],
                "message": f"commit {i}",
                "date": "2025-01-01",
            }
            for i in range(10)
        ]

        git = _mock_git_tool(base, fork_hashes, up_hashes, commits)
        detector = SyncPointDetector(
            sync_ratio_threshold=0.3, min_synced_files=5, enable_patch_id=False
        )
        result = detector.detect(git, "base_sha", "fork_ref", "upstream_ref")

        assert result.detected is True
        assert result.synced_file_count == 6
        assert result.upstream_changed_file_count == 10
        assert result.sync_ratio == 0.6
        assert result.effective_merge_base == "c5"
        assert result.first_unsynced_commit == "c6"
        assert result.skipped_commit_count == 6

    def test_no_upstream_changes_returns_not_detected(self):
        hashes = {"a.py": "h1"}
        git = _mock_git_tool(hashes, hashes, hashes)
        detector = SyncPointDetector(
            sync_ratio_threshold=0.3, min_synced_files=1, enable_patch_id=False
        )
        result = detector.detect(git, "base_sha", "fork_ref", "upstream_ref")
        assert result.detected is False
        assert result.sync_ratio == 0.0

    def test_empty_commit_files_are_skipped(self):
        base = {f"f{i}.py": f"base_{i}" for i in range(6)}
        fork = {f"f{i}.py": f"up_{i}" for i in range(6)}
        up = {f"f{i}.py": f"up_{i}" for i in range(6)}

        commits = [
            {"sha": "c0", "files": [], "message": "empty", "date": "2025-01-01"},
            {
                "sha": "c1",
                "files": ["f0.py", "f1.py"],
                "message": "real",
                "date": "2025-01-01",
            },
            {
                "sha": "c2",
                "files": ["f2.py", "f3.py", "f4.py", "f5.py"],
                "message": "real",
                "date": "2025-01-01",
            },
        ]

        git = _mock_git_tool(base, fork, up, commits)
        detector = SyncPointDetector(
            sync_ratio_threshold=0.3, min_synced_files=5, enable_patch_id=False
        )
        result = detector.detect(git, "base_sha", "fork_ref", "upstream_ref")

        assert result.detected is True
        assert result.effective_merge_base == "c2"
        assert result.skipped_commit_count == 3


class TestBinarySearchBoundary:
    def test_all_synced_binary(self):
        commits = [{"sha": f"c{i}", "files": [f"f{i}.py"]} for i in range(100)]
        synced = {f"f{i}.py" for i in range(100)}
        base, last, first_unsync, skipped = SyncPointDetector._binary_search_boundary(
            commits, synced, "base"
        )
        assert base == "c99"
        assert last == "c99"
        assert first_unsync is None
        assert skipped == 100

    def test_none_synced_binary(self):
        commits = [{"sha": "c0", "files": ["x.py"]}]
        synced: set[str] = set()
        base, last, first_unsync, skipped = SyncPointDetector._binary_search_boundary(
            commits, synced, "base"
        )
        assert base == "base"
        assert last is None
        assert first_unsync == "c0"
        assert skipped == 0

    def test_boundary_at_midpoint_binary(self):
        commits = [{"sha": f"c{i}", "files": [f"f{i}.py"]} for i in range(100)]
        synced = {f"f{i}.py" for i in range(50)}
        base, last, first_unsync, skipped = SyncPointDetector._binary_search_boundary(
            commits, synced, "base"
        )
        assert base == "c49"
        assert last == "c49"
        assert first_unsync == "c50"
        assert skipped == 50

    def test_dispatch_uses_binary_for_large(self):
        commits = [{"sha": f"c{i}", "files": [f"f{i}.py"]} for i in range(60)]
        synced = {f"f{i}.py" for i in range(30)}

        git = MagicMock()
        git.list_commits.return_value = commits

        base, last, first_unsync, skipped = (
            SyncPointDetector._commit_boundary_detection(git, "base", "up", synced)
        )
        assert base == "c29"
        assert skipped == 30

    def test_dispatch_uses_linear_for_small(self):
        commits = [
            {"sha": "c0", "files": ["a.py"]},
            {"sha": "c1", "files": ["b.py"]},
        ]
        synced = {"a.py", "b.py"}

        git = MagicMock()
        git.list_commits.return_value = commits

        base, last, first_unsync, skipped = (
            SyncPointDetector._commit_boundary_detection(git, "base", "up", synced)
        )
        assert base == "c1"
        assert skipped == 2


class TestLinearBoundary:
    def test_all_commits_synced(self):
        commits = [
            {"sha": "c1", "files": ["a.py"]},
            {"sha": "c2", "files": ["b.py"]},
        ]
        synced = {"a.py", "b.py"}
        base, last, first_unsync, skipped = SyncPointDetector._linear_boundary(
            commits, synced, "base"
        )
        assert base == "c2"
        assert last == "c2"
        assert first_unsync is None
        assert skipped == 2

    def test_no_commits_synced(self):
        commits = [{"sha": "c1", "files": ["x.py"]}]
        synced: set[str] = set()
        base, last, first_unsync, skipped = SyncPointDetector._linear_boundary(
            commits, synced, "base"
        )
        assert base == "base"
        assert last is None
        assert first_unsync == "c1"
        assert skipped == 0

    def test_boundary_at_midpoint(self):
        commits = [
            {"sha": "c1", "files": ["a.py"]},
            {"sha": "c2", "files": ["b.py"]},
            {"sha": "c3", "files": ["c.py"]},
        ]
        synced = {"a.py", "b.py"}
        base, last, first_unsync, skipped = SyncPointDetector._linear_boundary(
            commits, synced, "base"
        )
        assert base == "c2"
        assert last == "c2"
        assert first_unsync == "c3"
        assert skipped == 2


class TestConfidence:
    def test_high_confidence(self):
        detector = SyncPointDetector(sync_ratio_threshold=0.3, min_synced_files=5)
        conf = detector._compute_confidence(synced_count=20, sync_ratio=0.9)
        assert conf == 1.0

    def test_low_file_count_reduces_confidence(self):
        detector = SyncPointDetector(sync_ratio_threshold=0.3, min_synced_files=10)
        conf = detector._compute_confidence(synced_count=3, sync_ratio=0.9)
        assert conf < 1.0
        assert conf > 0.0

    def test_low_ratio_reduces_confidence(self):
        detector = SyncPointDetector(sync_ratio_threshold=0.5, min_synced_files=5)
        conf = detector._compute_confidence(synced_count=10, sync_ratio=0.3)
        assert conf < 1.0


class TestMigrationConfig:
    def test_default_migration_config(self):
        from src.models.config import MergeConfig

        config = MergeConfig(upstream_ref="upstream/main", fork_ref="fork/main")
        assert config.migration.auto_detect_sync_point is True
        assert config.migration.merge_base_override is None
        assert config.migration.sync_detection_threshold == 0.3
        assert config.migration.min_synced_files == 5

    def test_override_from_dict(self):
        from src.models.config import MergeConfig

        config = MergeConfig(
            upstream_ref="upstream/main",
            fork_ref="fork/main",
            migration={
                "merge_base_override": "abc123",
                "auto_detect_sync_point": False,
                "sync_detection_threshold": 0.15,
                "min_synced_files": 3,
            },
        )
        assert config.migration.merge_base_override == "abc123"
        assert config.migration.auto_detect_sync_point is False
        assert config.migration.sync_detection_threshold == 0.15
        assert config.migration.min_synced_files == 3

    def test_threshold_validation(self):
        from src.models.config import MigrationConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MigrationConfig(sync_detection_threshold=1.5)

        with pytest.raises(ValidationError):
            MigrationConfig(sync_detection_threshold=-0.1)

    def test_min_synced_files_validation(self):
        from src.models.config import MigrationConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MigrationConfig(min_synced_files=0)


class TestMergeStateWithMigration:
    def test_migration_info_default_none(self):
        from src.models.config import MergeConfig
        from src.models.state import MergeState

        state = MergeState(config=MergeConfig(upstream_ref="up", fork_ref="fork"))
        assert state.migration_info is None

    def test_migration_info_roundtrip(self):
        from src.models.config import MergeConfig
        from src.models.state import MergeState

        result = SyncPointResult(
            detected=True,
            effective_merge_base="abc",
            git_merge_base="def",
            synced_file_count=5,
            upstream_changed_file_count=10,
            sync_ratio=0.5,
            confidence=0.8,
        )
        state = MergeState(
            config=MergeConfig(upstream_ref="up", fork_ref="fork"),
            migration_info=result,
        )
        data = state.model_dump(mode="json")
        restored = MergeState.model_validate(data)
        assert restored.migration_info is not None
        assert restored.migration_info.detected is True
        assert restored.migration_info.synced_file_count == 5
