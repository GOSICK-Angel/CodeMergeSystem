from __future__ import annotations

import logging
from datetime import datetime

from src.core.phases.base import Phase, PhaseContext, PhaseOutcome
from src.models.conflict import ConflictAnalysis, ConflictType
from src.models.config import ThresholdConfig
from src.models.decision import MergeDecision
from src.models.diff import FileDiff
from src.models.human import HumanDecisionRequest, DecisionOption
from src.models.plan import MergePhase
from src.models.state import MergeState, PhaseResult, SystemStatus

logger = logging.getLogger(__name__)


def _select_merge_strategy(
    analysis: ConflictAnalysis, thresholds: ThresholdConfig
) -> MergeDecision:
    if analysis.confidence < thresholds.human_escalation:
        return MergeDecision.ESCALATE_HUMAN

    if analysis.conflict_type == ConflictType.LOGIC_CONTRADICTION:
        if analysis.confidence < 0.90:
            return MergeDecision.ESCALATE_HUMAN

    if analysis.conflict_type == ConflictType.SEMANTIC_EQUIVALENT:
        if analysis.confidence >= thresholds.auto_merge_confidence:
            return MergeDecision.TAKE_TARGET

    if analysis.can_coexist and analysis.confidence >= thresholds.auto_merge_confidence:
        return MergeDecision.SEMANTIC_MERGE

    if analysis.is_security_sensitive:
        return MergeDecision.ESCALATE_HUMAN

    if analysis.confidence >= thresholds.auto_merge_confidence:
        return analysis.recommended_strategy

    return MergeDecision.ESCALATE_HUMAN


def _build_human_decision_request(
    fd: FileDiff, analysis: ConflictAnalysis
) -> HumanDecisionRequest:
    rec_val = analysis.recommended_strategy

    options = [
        DecisionOption(
            option_key="A",
            decision=MergeDecision.TAKE_CURRENT,
            description="Keep fork (current) version",
        ),
        DecisionOption(
            option_key="B",
            decision=MergeDecision.TAKE_TARGET,
            description="Take upstream (target) version",
        ),
        DecisionOption(
            option_key="C",
            decision=MergeDecision.SEMANTIC_MERGE,
            description="Attempt semantic merge",
        ),
        DecisionOption(
            option_key="D",
            decision=MergeDecision.MANUAL_PATCH,
            description="Provide custom content",
        ),
    ]

    return HumanDecisionRequest(
        file_path=fd.file_path,
        priority=1 if fd.is_security_sensitive else 5,
        conflict_points=analysis.conflict_points,
        context_summary=f"File {fd.file_path} has conflicts requiring human review",
        upstream_change_summary=f"Upstream added {fd.lines_added} lines",
        fork_change_summary=f"Fork deleted {fd.lines_deleted} lines",
        analyst_recommendation=rec_val,
        analyst_confidence=analysis.confidence,
        analyst_rationale=analysis.rationale,
        options=options,
        created_at=datetime.now(),
    )


class ConflictAnalysisPhase(Phase):
    name = "conflict_analysis"

    async def execute(self, state: MergeState, ctx: PhaseContext) -> PhaseOutcome:
        state.current_phase = MergePhase.CONFLICT_ANALYSIS
        phase_result = PhaseResult(
            phase=MergePhase.CONFLICT_ANALYSIS,
            status="running",
            started_at=datetime.now(),
        )
        state.phase_results[MergePhase.CONFLICT_ANALYSIS.value] = phase_result

        conflict_analyst = ctx.agents["conflict_analyst"]
        executor = ctx.agents["executor"]
        await conflict_analyst.run(state)

        file_diffs_map: dict[str, FileDiff] = {}
        for fd in getattr(state, "_file_diffs", None) or []:
            file_diffs_map[fd.file_path] = fd

        needs_human: list[str] = []
        for file_path, analysis in state.conflict_analyses.items():
            fd = file_diffs_map.get(file_path)
            if fd is None:
                continue

            strategy = _select_merge_strategy(analysis, state.config.thresholds)

            if strategy == MergeDecision.ESCALATE_HUMAN:
                needs_human.append(file_path)
                req = _build_human_decision_request(fd, analysis)
                state.human_decision_requests[file_path] = req
            elif strategy == MergeDecision.SEMANTIC_MERGE:
                record = await executor.execute_semantic_merge(fd, analysis, state)
                state.file_decision_records[file_path] = record
                ctx.checkpoint.save(state, f"phase3_{file_path.replace('/', '_')}")
            else:
                record = await executor.execute_auto_merge(fd, strategy, state)
                state.file_decision_records[file_path] = record

        phase_result = phase_result.model_copy(
            update={"status": "completed", "completed_at": datetime.now()}
        )
        state.phase_results[MergePhase.CONFLICT_ANALYSIS.value] = phase_result

        if needs_human:
            ctx.state_machine.transition(
                state,
                SystemStatus.AWAITING_HUMAN,
                f"{len(needs_human)} files need human review",
            )
            return PhaseOutcome(
                target_status=SystemStatus.AWAITING_HUMAN,
                reason=f"{len(needs_human)} files need human review",
                checkpoint_tag="after_phase3",
                memory_phase="conflict_analysis",
            )
        else:
            ctx.state_machine.transition(
                state,
                SystemStatus.JUDGE_REVIEWING,
                "conflict analysis complete",
            )
            return PhaseOutcome(
                target_status=SystemStatus.JUDGE_REVIEWING,
                reason="conflict analysis complete",
                checkpoint_tag="after_phase3",
                memory_phase="conflict_analysis",
            )
