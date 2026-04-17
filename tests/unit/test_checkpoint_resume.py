"""Tests for checkpoint serialization round-trip and resume correctness."""

import json
from pathlib import Path

import pytest

from src.core.checkpoint import Checkpoint
from src.models.config import MergeConfig
from src.models.diff import (
    FileDiff,
    FileChangeCategory,
    FileStatus,
    RiskLevel,
)
from src.models.state import MergeState, SystemStatus


def _make_config() -> MergeConfig:
    return MergeConfig(
        upstream_ref="upstream/main",
        fork_ref="feature/fork",
    )


def _make_file_diff(
    file_path: str = "src/foo.py",
    risk_level: RiskLevel = RiskLevel.AUTO_SAFE,
) -> FileDiff:
    return FileDiff(
        file_path=file_path,
        file_status=FileStatus.MODIFIED,
        risk_level=risk_level,
        risk_score=0.35,
        lines_added=10,
        lines_deleted=3,
        change_category=FileChangeCategory.C,
        language="python",
        is_security_sensitive=False,
    )


def _make_state_with_diffs() -> MergeState:
    state = MergeState(config=_make_config())
    state.file_diffs = [
        _make_file_diff("src/auth.py", RiskLevel.HUMAN_REQUIRED),
        _make_file_diff("src/utils.py", RiskLevel.AUTO_SAFE),
        _make_file_diff("src/config.py", RiskLevel.AUTO_RISKY),
    ]
    state.upstream_commits = [
        {"sha": "abc123", "message": "feat: add auth", "files": ["src/auth.py"]},
        {"sha": "def456", "message": "fix: utils", "files": ["src/utils.py"]},
    ]
    state.replayable_commits = [
        {"sha": "def456", "message": "fix: utils", "files": ["src/utils.py"]},
    ]
    state.non_replayable_commits = [
        {"sha": "abc123", "message": "feat: add auth", "files": ["src/auth.py"]},
    ]
    state.status = SystemStatus.PLANNING
    state.file_categories = {
        "src/auth.py": FileChangeCategory.C,
        "src/utils.py": FileChangeCategory.B,
        "src/config.py": FileChangeCategory.C,
    }
    return state


class TestCheckpointRoundTrip:
    def test_file_diffs_survive_serialization(self, tmp_path: Path):
        state = _make_state_with_diffs()
        cp = Checkpoint(tmp_path)

        cp.save(state, "test_tag")
        loaded = cp.load(cp.get_latest())

        assert len(loaded.file_diffs) == 3
        assert loaded.file_diffs[0].file_path == "src/auth.py"
        assert loaded.file_diffs[0].risk_level == RiskLevel.HUMAN_REQUIRED
        assert loaded.file_diffs[1].risk_score == 0.35
        assert loaded.file_diffs[2].change_category == FileChangeCategory.C

    def test_upstream_commits_survive_serialization(self, tmp_path: Path):
        state = _make_state_with_diffs()
        cp = Checkpoint(tmp_path)

        cp.save(state, "test_tag")
        loaded = cp.load(cp.get_latest())

        assert len(loaded.upstream_commits) == 2
        assert loaded.upstream_commits[0]["sha"] == "abc123"
        assert loaded.upstream_commits[1]["message"] == "fix: utils"

    def test_replayable_commits_survive_serialization(self, tmp_path: Path):
        state = _make_state_with_diffs()
        cp = Checkpoint(tmp_path)

        cp.save(state, "test_tag")
        loaded = cp.load(cp.get_latest())

        assert len(loaded.replayable_commits) == 1
        assert loaded.replayable_commits[0]["sha"] == "def456"
        assert len(loaded.non_replayable_commits) == 1
        assert loaded.non_replayable_commits[0]["sha"] == "abc123"

    def test_status_and_categories_survive(self, tmp_path: Path):
        state = _make_state_with_diffs()
        cp = Checkpoint(tmp_path)

        cp.save(state, "test_tag")
        loaded = cp.load(cp.get_latest())

        assert loaded.status == SystemStatus.PLANNING
        assert loaded.run_id == state.run_id
        assert loaded.file_categories["src/auth.py"] == FileChangeCategory.C
        assert loaded.file_categories["src/utils.py"] == FileChangeCategory.B

    def test_empty_diffs_survive(self, tmp_path: Path):
        state = MergeState(config=_make_config())
        cp = Checkpoint(tmp_path)

        cp.save(state, "empty")
        loaded = cp.load(cp.get_latest())

        assert loaded.file_diffs == []
        assert loaded.upstream_commits == []
        assert loaded.replayable_commits == []
        assert loaded.non_replayable_commits == []

    def test_full_state_round_trip_preserves_run_id(self, tmp_path: Path):
        state = _make_state_with_diffs()
        original_run_id = state.run_id
        cp = Checkpoint(tmp_path)

        cp.save(state, "full")
        loaded = cp.load(cp.get_latest())

        assert loaded.run_id == original_run_id
        assert loaded.config.upstream_ref == "upstream/main"
        assert loaded.config.fork_ref == "feature/fork"


class TestCheckpointErrorHandling:
    def test_load_nonexistent_raises_file_not_found(self, tmp_path: Path):
        cp = Checkpoint(tmp_path)
        with pytest.raises(FileNotFoundError):
            cp.load(tmp_path / "does_not_exist.json")

    def test_load_corrupted_json_raises_runtime_error(self, tmp_path: Path):
        cp = Checkpoint(tmp_path)
        bad_file = cp.run_dir / "corrupted.json"
        bad_file.write_text("{invalid json", encoding="utf-8")

        with pytest.raises(RuntimeError, match="corrupted"):
            cp.load(bad_file)

    def test_load_invalid_schema_raises_runtime_error(self, tmp_path: Path):
        cp = Checkpoint(tmp_path)
        bad_file = cp.run_dir / "bad_schema.json"
        bad_file.write_text(json.dumps({"not_a_valid": "state"}), encoding="utf-8")

        with pytest.raises(RuntimeError, match="schema mismatch"):
            cp.load(bad_file)


class TestAtomicWrite:
    def test_atomic_write_no_partial_file_on_success(self, tmp_path: Path):
        state = _make_state_with_diffs()
        cp = Checkpoint(tmp_path)

        saved_path = cp.save(state, "atomic_test")

        assert saved_path.exists()
        assert not saved_path.with_suffix(".tmp").exists()

        loaded = cp.load(saved_path)
        assert len(loaded.file_diffs) == 3
