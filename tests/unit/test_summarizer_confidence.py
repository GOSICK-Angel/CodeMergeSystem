"""Tests for PhaseSummarizer confidence_level assignment."""

from src.memory.models import ConfidenceLevel, MemoryEntryType
from src.memory.summarizer import PhaseSummarizer
from src.models.config import MergeConfig
from src.models.conflict import ConflictAnalysis, ConflictType
from src.models.decision import (
    DecisionSource,
    FileDecisionRecord,
    MergeDecision,
)
from src.models.diff import FileChangeCategory, FileStatus
from src.models.state import MergeState


def _make_state() -> MergeState:
    config = MergeConfig(upstream_ref="upstream/main", fork_ref="feature/fork")
    return MergeState(config=config)


class TestPlanningConfidenceLevel:
    def test_planning_entries_are_extracted(self):
        state = _make_state()
        state.file_categories = {
            f"api/models/file{i}.py": FileChangeCategory.C for i in range(5)
        }
        summarizer = PhaseSummarizer()
        _, entries = summarizer.summarize_planning(state)

        assert len(entries) >= 1
        for entry in entries:
            assert entry.confidence_level == ConfidenceLevel.EXTRACTED


class TestAutoMergeConfidenceLevel:
    def test_auto_merge_entries_are_inferred(self):
        state = _make_state()
        for i in range(5):
            fp = f"vendor/libs/lib{i}.py"
            state.file_decision_records[fp] = FileDecisionRecord(
                file_path=fp,
                decision=MergeDecision.TAKE_TARGET,
                decision_source=DecisionSource.AUTO_EXECUTOR,
                rationale="auto",
                file_status=FileStatus.MODIFIED,
            )
        summarizer = PhaseSummarizer()
        _, entries = summarizer.summarize_auto_merge(state)

        assert len(entries) >= 1
        for entry in entries:
            assert entry.confidence_level == ConfidenceLevel.INFERRED


class TestConflictAnalysisConfidenceLevel:
    def test_conflict_entries_are_extracted(self):
        state = _make_state()
        for i in range(4):
            fp = f"src/core/file{i}.py"
            state.conflict_analyses[fp] = ConflictAnalysis(
                file_path=fp,
                conflict_type=ConflictType.CONCURRENT_MODIFICATION,
                recommended_strategy=MergeDecision.ESCALATE_HUMAN,
                conflict_points=[],
                overall_confidence=0.8,
            )
        summarizer = PhaseSummarizer()
        _, entries = summarizer.summarize_conflict_analysis(state)

        assert len(entries) >= 1
        for entry in entries:
            assert entry.confidence_level == ConfidenceLevel.EXTRACTED


class TestJudgeReviewConfidenceLevel:
    def test_judge_entries_are_heuristic(self):
        state = _make_state()
        state.judge_verdicts_log = [
            {
                "verdict": "needs_repair",
                "issues": [
                    {"issue_type": "syntax_error"},
                    {"issue_type": "syntax_error"},
                ],
            },
            {
                "verdict": "needs_repair",
                "issues": [
                    {"issue_type": "syntax_error"},
                ],
            },
        ]
        summarizer = PhaseSummarizer()
        _, entries = summarizer.summarize_judge_review(state)

        assert len(entries) >= 1
        for entry in entries:
            assert entry.confidence_level == ConfidenceLevel.HEURISTIC
