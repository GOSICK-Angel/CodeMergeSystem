"""Coordinator — decision router for abnormal phase outcomes.

Extracts three kinds of "judgment work" from Phase classes so that Phases
only handle their own happy-path logic:

1. route_judge_stall  — when JudgeReviewPhase exhausts repair rounds
2. route_dispute      — when AutoMergePhase receives a plan dispute
3. enforce_batch_limits — splits oversized PhaseFileBatches after planning

The Coordinator never calls LLM directly; meta-review calls go through
existing Agent methods (PlannerAgent.meta_review / JudgeAgent.meta_review).
"""

from __future__ import annotations

import logging
from uuid import uuid4

from src.llm.context import get_context_window
from src.models.config import MergeConfig
from src.models.coordinator import CoordinatorDecision, MetaReviewResult
from src.models.dispute import PlanDisputeRequest
from src.models.plan import MergePlan, PhaseFileBatch
from src.models.state import MergeState

logger = logging.getLogger(__name__)


class Coordinator:
    """Service class that makes routing decisions for Phases."""

    def __init__(self, config: MergeConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # ① Routing
    # ------------------------------------------------------------------

    def route_judge_stall(self, state: MergeState) -> CoordinatorDecision:
        """Decide what to do when Judge repair rounds are exhausted."""
        cfg = self._config.coordinator
        rounds = state.judge_repair_rounds + 1

        if cfg.meta_review_enabled and rounds >= cfg.judge_meta_review_threshold:
            logger.info(
                "Coordinator: judge stalled after %d rounds (threshold=%d) → meta_review",
                rounds,
                cfg.judge_meta_review_threshold,
            )
            return CoordinatorDecision(
                action="meta_review",
                reason=(
                    f"Judge did not converge after {rounds} rounds "
                    f"(threshold={cfg.judge_meta_review_threshold})"
                ),
                meta_gate="META-JUDGE-REVIEW",
            )

        logger.info(
            "Coordinator: judge stalled after %d rounds → escalate_human", rounds
        )
        return CoordinatorDecision(
            action="escalate_human",
            reason=f"Judge did not converge after {rounds} rounds",
        )

    def route_dispute(
        self, state: MergeState, dispute: PlanDisputeRequest
    ) -> CoordinatorDecision:
        """Decide what to do when an Executor plan dispute arrives."""
        cfg = self._config.coordinator
        dispute_count = len(state.plan_disputes)

        if (
            cfg.meta_review_enabled
            and dispute_count >= cfg.dispute_meta_review_threshold
        ):
            logger.info(
                "Coordinator: %d disputes (threshold=%d) → meta_review",
                dispute_count,
                cfg.dispute_meta_review_threshold,
            )
            return CoordinatorDecision(
                action="meta_review",
                reason=(
                    f"Plan dispute #{dispute_count} reached threshold "
                    f"({cfg.dispute_meta_review_threshold})"
                ),
                meta_gate="META-PLAN-REVIEW",
            )

        logger.info(
            "Coordinator: dispute #%d → continue standard revision", dispute_count
        )
        return CoordinatorDecision(
            action="continue",
            reason=f"Plan dispute #{dispute_count} — standard revision",
        )

    # ------------------------------------------------------------------
    # ② Batch-size enforcement
    # ------------------------------------------------------------------

    def compute_max_batch_size(self, model: str) -> int:
        """Return the maximum number of files per PhaseFileBatch."""
        cfg = self._config.coordinator
        if cfg.max_files_per_batch is not None:
            return cfg.max_files_per_batch
        window = get_context_window(model)
        raw = int(window * cfg.context_utilization_ratio / cfg.avg_tokens_per_file)
        return max(1, raw)

    def enforce_batch_limits(self, plan: MergePlan) -> MergePlan:
        """Split any PhaseFileBatch that exceeds the computed size cap.

        Uses the planner's configured model for context window lookup.
        Returns a new MergePlan if any batch was split; otherwise returns
        the original plan unchanged.
        """
        model = self._config.agents.planner.model
        max_size = self.compute_max_batch_size(model)

        new_phases: list[PhaseFileBatch] = []
        changed = False
        for batch in plan.phases:
            if len(batch.file_paths) <= max_size:
                new_phases.append(batch)
                continue

            changed = True
            sub_count = 0
            for i in range(0, len(batch.file_paths), max_size):
                sub_paths = batch.file_paths[i : i + max_size]
                new_phases.append(
                    batch.model_copy(
                        update={"batch_id": str(uuid4()), "file_paths": sub_paths}
                    )
                )
                sub_count += 1

            logger.info(
                "Coordinator: split batch %s (%d files) into %d sub-batches "
                "(max_size=%d)",
                batch.batch_id,
                len(batch.file_paths),
                sub_count,
                max_size,
            )

        if not changed:
            return plan
        return plan.model_copy(update={"phases": new_phases})

    # ------------------------------------------------------------------
    # ③ Meta-review result builder
    # ------------------------------------------------------------------

    @staticmethod
    def build_meta_review_result(
        phase: str,
        trigger: str,
        raw: dict[str, str],
    ) -> MetaReviewResult:
        return MetaReviewResult(
            phase=phase,
            trigger=trigger,  # type: ignore[arg-type]
            assessment=raw.get("assessment", "")[:200],
            recommendation=raw.get("recommendation", "")[:200],
        )
