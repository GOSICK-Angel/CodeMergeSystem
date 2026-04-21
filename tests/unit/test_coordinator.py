"""Unit tests for src/core/coordinator.py"""

from __future__ import annotations

import pytest
from uuid import uuid4

from src.core.coordinator import Coordinator
from src.models.config import MergeConfig
from src.models.coordinator import CoordinatorDecision, MetaReviewResult
from src.models.dispute import PlanDisputeRequest
from src.models.plan import MergePlan, MergePhase, PhaseFileBatch, RiskSummary
from src.models.state import MergeState
from src.models.diff import RiskLevel


def _make_config(**overrides) -> MergeConfig:
    cfg = MergeConfig(upstream_ref="upstream/main", fork_ref="feature/fork")
    if overrides:
        cfg = cfg.model_copy(deep=True, update=overrides)
    return cfg


def _make_state(config: MergeConfig | None = None) -> MergeState:
    return MergeState(config=config or _make_config())


def _make_batch(file_paths: list[str]) -> PhaseFileBatch:
    return PhaseFileBatch(
        batch_id=str(uuid4()),
        phase=MergePhase.AUTO_MERGE,
        file_paths=file_paths,
        risk_level=RiskLevel.AUTO_SAFE,
    )


def _make_plan(batches: list[PhaseFileBatch]) -> MergePlan:
    from datetime import datetime

    return MergePlan(
        created_at=datetime.now(),
        upstream_ref="upstream/main",
        fork_ref="feature/fork",
        merge_base_commit="abc123",
        phases=batches,
        risk_summary=RiskSummary(
            total_files=sum(len(b.file_paths) for b in batches),
            auto_safe_count=0,
            auto_risky_count=0,
            human_required_count=0,
            deleted_only_count=0,
            binary_count=0,
            excluded_count=0,
            estimated_auto_merge_rate=1.0,
        ),
        project_context_summary="test",
    )


def _make_dispute(reason: str = "risk underestimated") -> PlanDisputeRequest:
    return PlanDisputeRequest(
        phase="auto_merge",
        disputed_files=["src/foo.py"],
        dispute_reason=reason,
        suggested_reclassification={},
        impact_assessment="test",
    )


class TestRouteJudgeStall:
    def test_below_threshold_escalates_human(self):
        cfg = _make_config()
        cfg.coordinator.judge_meta_review_threshold = 3
        state = _make_state(cfg)
        state.judge_repair_rounds = 1  # rounds done = 2, below threshold 3

        c = Coordinator(cfg)
        decision = c.route_judge_stall(state)

        assert decision.action == "escalate_human"
        assert decision.meta_gate is None

    def test_at_threshold_triggers_meta_review(self):
        cfg = _make_config()
        cfg.coordinator.judge_meta_review_threshold = 2
        state = _make_state(cfg)
        state.judge_repair_rounds = 1  # rounds done = 2, equals threshold

        c = Coordinator(cfg)
        decision = c.route_judge_stall(state)

        assert decision.action == "meta_review"
        assert decision.meta_gate == "META-JUDGE-REVIEW"

    def test_meta_review_disabled_falls_back_to_escalate(self):
        cfg = _make_config()
        cfg.coordinator.meta_review_enabled = False
        cfg.coordinator.judge_meta_review_threshold = 1
        state = _make_state(cfg)
        state.judge_repair_rounds = 5

        c = Coordinator(cfg)
        decision = c.route_judge_stall(state)

        assert decision.action == "escalate_human"


class TestRouteDispute:
    def test_below_threshold_continues(self):
        cfg = _make_config()
        cfg.coordinator.dispute_meta_review_threshold = 3
        state = _make_state(cfg)
        state.plan_disputes = [_make_dispute(), _make_dispute()]  # count = 2

        c = Coordinator(cfg)
        decision = c.route_dispute(state, _make_dispute())

        assert decision.action == "continue"

    def test_at_threshold_triggers_meta_review(self):
        cfg = _make_config()
        cfg.coordinator.dispute_meta_review_threshold = 2
        state = _make_state(cfg)
        state.plan_disputes = [_make_dispute(), _make_dispute()]  # count = 2

        c = Coordinator(cfg)
        decision = c.route_dispute(state, _make_dispute())

        assert decision.action == "meta_review"
        assert decision.meta_gate == "META-PLAN-REVIEW"

    def test_meta_review_disabled_always_continues(self):
        cfg = _make_config()
        cfg.coordinator.meta_review_enabled = False
        cfg.coordinator.dispute_meta_review_threshold = 1
        state = _make_state(cfg)
        state.plan_disputes = [_make_dispute() for _ in range(10)]

        c = Coordinator(cfg)
        decision = c.route_dispute(state, _make_dispute())

        assert decision.action == "continue"


class TestEnforceBatchLimits:
    def test_small_batches_unchanged(self):
        cfg = _make_config()
        cfg.coordinator.max_files_per_batch = 10
        batch = _make_batch([f"file_{i}.py" for i in range(5)])
        plan = _make_plan([batch])

        c = Coordinator(cfg)
        result = c.enforce_batch_limits(plan)

        assert result is plan  # no copy made

    def test_large_batch_is_split(self):
        cfg = _make_config()
        cfg.coordinator.max_files_per_batch = 3
        files = [f"file_{i}.py" for i in range(10)]
        batch = _make_batch(files)
        plan = _make_plan([batch])

        c = Coordinator(cfg)
        result = c.enforce_batch_limits(plan)

        assert result is not plan
        assert len(result.phases) == 4  # ceil(10/3) = 4
        total = sum(len(b.file_paths) for b in result.phases)
        assert total == 10

    def test_split_preserves_risk_level(self):
        cfg = _make_config()
        cfg.coordinator.max_files_per_batch = 2
        batch = _make_batch(["a.py", "b.py", "c.py"])
        batch = batch.model_copy(update={"risk_level": RiskLevel.AUTO_RISKY})
        plan = _make_plan([batch])

        c = Coordinator(cfg)
        result = c.enforce_batch_limits(plan)

        for sub in result.phases:
            assert sub.risk_level == RiskLevel.AUTO_RISKY

    def test_split_batches_have_unique_ids(self):
        cfg = _make_config()
        cfg.coordinator.max_files_per_batch = 2
        plan = _make_plan([_make_batch([f"f{i}.py" for i in range(6)])])

        c = Coordinator(cfg)
        result = c.enforce_batch_limits(plan)

        ids = [b.batch_id for b in result.phases]
        assert len(ids) == len(set(ids))

    def test_compute_max_batch_size_respects_hard_cap(self):
        cfg = _make_config()
        cfg.coordinator.max_files_per_batch = 7
        c = Coordinator(cfg)
        assert c.compute_max_batch_size("claude-opus-4-6") == 7

    def test_compute_max_batch_size_auto(self):
        cfg = _make_config()
        cfg.coordinator.max_files_per_batch = None
        cfg.coordinator.context_utilization_ratio = 0.5
        cfg.coordinator.avg_tokens_per_file = 1000
        c = Coordinator(cfg)
        size = c.compute_max_batch_size("claude-opus-4-6")
        # 200_000 * 0.5 / 1000 = 100
        assert size == 100


class TestBuildMetaReviewResult:
    def test_fields_populated(self):
        raw = {"assessment": "root cause", "recommendation": "try this"}
        result = Coordinator.build_meta_review_result(
            phase="judge_review", trigger="judge_stall", raw=raw
        )
        assert isinstance(result, MetaReviewResult)
        assert result.phase == "judge_review"
        assert result.trigger == "judge_stall"
        assert result.assessment == "root cause"
        assert result.recommendation == "try this"

    def test_truncates_long_strings(self):
        raw = {
            "assessment": "x" * 300,
            "recommendation": "y" * 300,
        }
        result = Coordinator.build_meta_review_result(
            phase="auto_merge", trigger="plan_dispute", raw=raw
        )
        assert len(result.assessment) <= 200
        assert len(result.recommendation) <= 200
