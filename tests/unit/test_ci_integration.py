import json

from src.cli.exit_codes import (
    EXIT_SUCCESS,
    EXIT_NEEDS_HUMAN,
    EXIT_JUDGE_REJECTED,
    EXIT_PARTIAL_FAILURE,
    EXIT_CONFIG_ERROR,
    EXIT_GIT_ERROR,
    EXIT_LLM_ERROR,
    EXIT_UNKNOWN_ERROR,
)
from src.tools.ci_reporter import build_ci_summary, format_ci_summary
from src.models.state import MergeState, SystemStatus
from src.models.config import MergeConfig


def _make_config() -> MergeConfig:
    return MergeConfig(upstream_ref="upstream/main", fork_ref="fork/main")


class TestExitCodes:
    def test_exit_codes_unique(self) -> None:
        codes = [
            EXIT_SUCCESS,
            EXIT_NEEDS_HUMAN,
            EXIT_JUDGE_REJECTED,
            EXIT_PARTIAL_FAILURE,
            EXIT_CONFIG_ERROR,
            EXIT_GIT_ERROR,
            EXIT_LLM_ERROR,
            EXIT_UNKNOWN_ERROR,
        ]
        assert len(codes) == len(set(codes))

    def test_success_is_zero(self) -> None:
        assert EXIT_SUCCESS == 0

    def test_unknown_is_one(self) -> None:
        assert EXIT_UNKNOWN_ERROR == 1


class TestCIReporter:
    def test_completed_state(self) -> None:
        state = MergeState(config=_make_config())
        state.status = SystemStatus.COMPLETED
        summary = build_ci_summary(state)
        assert summary["status"] == "success"
        assert summary["run_id"] == state.run_id

    def test_awaiting_human_state(self) -> None:
        state = MergeState(config=_make_config())
        state.status = SystemStatus.AWAITING_HUMAN
        summary = build_ci_summary(state)
        assert summary["status"] == "needs_human"

    def test_failed_state(self) -> None:
        state = MergeState(config=_make_config())
        state.status = SystemStatus.FAILED
        summary = build_ci_summary(state)
        assert summary["status"] == "failed"

    def test_summary_format_is_valid_json(self) -> None:
        state = MergeState(config=_make_config())
        state.status = SystemStatus.COMPLETED
        summary = build_ci_summary(state)
        formatted = format_ci_summary(summary)
        parsed = json.loads(formatted)
        assert parsed["status"] == "success"

    def test_summary_includes_counts(self) -> None:
        state = MergeState(config=_make_config())
        state.status = SystemStatus.COMPLETED
        summary = build_ci_summary(state)
        assert "total_files" in summary
        assert "auto_merged" in summary
        assert "human_required" in summary
        assert "judge_verdict" in summary

    def test_summary_with_errors(self) -> None:
        state = MergeState(config=_make_config())
        state.status = SystemStatus.COMPLETED
        state.errors = [{"message": "some error", "phase": "test"}]
        summary = build_ci_summary(state)
        assert summary["status"] == "partial_failure"
        assert summary["failed_count"] == 1
        assert "some error" in summary["errors"]

    def test_judge_verdict_included(self) -> None:
        from datetime import datetime

        from src.models.judge import JudgeVerdict, VerdictType

        state = MergeState(config=_make_config())
        state.status = SystemStatus.COMPLETED
        state.judge_verdict = JudgeVerdict(
            verdict=VerdictType.PASS,
            reviewed_files_count=5,
            passed_files=["a.py"],
            failed_files=[],
            conditional_files=[],
            issues=[],
            critical_issues_count=0,
            high_issues_count=0,
            overall_confidence=0.9,
            summary="All good",
            blocking_issues=[],
            timestamp=datetime.now(),
            judge_model="test",
        )
        summary = build_ci_summary(state)
        assert summary["judge_verdict"] == "pass"

    def test_unknown_status(self) -> None:
        state = MergeState(config=_make_config())
        state.status = SystemStatus.PLANNING
        summary = build_ci_summary(state)
        assert summary["status"] == "unknown"

    def test_errors_limited_to_last_five(self) -> None:
        state = MergeState(config=_make_config())
        state.status = SystemStatus.FAILED
        state.errors = [{"message": f"error {i}"} for i in range(10)]
        summary = build_ci_summary(state)
        assert len(summary["errors"]) == 5
        assert summary["errors"][0] == "error 5"
