from __future__ import annotations

import logging
from datetime import datetime

from src.core.phases.base import Phase, PhaseContext, PhaseOutcome
from src.models.diff import FileDiff
from src.models.plan import MergePhase
from src.models.plan_judge import PlanJudgeResult
from src.models.plan_review import PlanReviewRound
from src.models.state import MergeState, PhaseResult, SystemStatus
from src.tools.report_writer import write_plan_review_report

logger = logging.getLogger(__name__)


class PlanReviewPhase(Phase):
    name = "plan_review"

    async def execute(self, state: MergeState, ctx: PhaseContext) -> PhaseOutcome:
        state.current_phase = MergePhase.PLAN_REVIEW
        phase_result = PhaseResult(
            phase=MergePhase.PLAN_REVIEW,
            status="running",
            started_at=datetime.now(),
        )
        state.phase_results[MergePhase.PLAN_REVIEW.value] = phase_result

        planner = ctx.agents["planner"]
        planner_judge = ctx.agents["planner_judge"]
        file_diffs: list[FileDiff] = getattr(state, "_file_diffs", []) or []
        max_rounds = ctx.config.max_plan_revision_rounds

        for round_num in range(max_rounds + 1):
            state.plan_revision_rounds = round_num

            assert state.merge_plan is not None
            verdict = await planner_judge.review_plan(
                state.merge_plan,
                file_diffs,
                round_num,
                lang=ctx.config.output.language,
            )
            state.plan_judge_verdict = verdict

            round_log = PlanReviewRound(
                round_number=round_num,
                verdict_result=verdict.result,
                verdict_summary=verdict.summary,
                issues_count=len(verdict.issues),
                issues_detail=[
                    {
                        "file_path": issue.file_path,
                        "reason": issue.reason,
                        "current": issue.current_classification.value
                        if hasattr(issue.current_classification, "value")
                        else str(issue.current_classification),
                        "suggested": issue.suggested_classification.value
                        if hasattr(issue.suggested_classification, "value")
                        else str(issue.suggested_classification),
                    }
                    for issue in verdict.issues
                ],
            )

            is_llm_failure = (
                len(verdict.issues) == 0
                and verdict.summary
                and "parse failed" in verdict.summary.lower()
            )
            if is_llm_failure:
                state.plan_review_log.append(round_log)
                phase_result = phase_result.model_copy(
                    update={"status": "completed", "completed_at": datetime.now()}
                )
                state.phase_results[MergePhase.PLAN_REVIEW.value] = phase_result
                write_plan_review_report(state, ctx.config.output.directory)
                logger.warning(
                    "Plan judge LLM call failed (round %d) — "
                    "skipping review, proceeding with current plan",
                    round_num,
                )
                ctx.state_machine.transition(
                    state,
                    SystemStatus.AWAITING_HUMAN,
                    "plan judge LLM unavailable, proceeding with current plan",
                )
                return PhaseOutcome(
                    target_status=SystemStatus.AWAITING_HUMAN,
                    reason="plan judge LLM unavailable",
                    checkpoint_tag="after_phase1_5",
                )

            if verdict.result == PlanJudgeResult.APPROVED:
                state.plan_review_log.append(round_log)
                phase_result = phase_result.model_copy(
                    update={"status": "completed", "completed_at": datetime.now()}
                )
                state.phase_results[MergePhase.PLAN_REVIEW.value] = phase_result
                write_plan_review_report(state, ctx.config.output.directory)
                logger.info("Plan approved by judge — proceeding to auto-merge")
                ctx.state_machine.transition(
                    state,
                    SystemStatus.AWAITING_HUMAN,
                    "plan approved by judge",
                )
                return PhaseOutcome(
                    target_status=SystemStatus.AWAITING_HUMAN,
                    reason="plan approved by judge",
                    checkpoint_tag="after_phase1_5",
                )

            elif verdict.result == PlanJudgeResult.CRITICAL_REPLAN:
                state.plan_review_log.append(round_log)
                ctx.state_machine.transition(
                    state, SystemStatus.PLANNING, "critical replan required"
                )
                from src.core.phases.planning import PlanningPhase

                planning = PlanningPhase()
                await planning.execute(state, ctx)
                return PhaseOutcome(
                    target_status=state.status,
                    reason="critical replan executed",
                    checkpoint_tag="after_phase1_5",
                )

            elif round_num < max_rounds:
                ctx.state_machine.transition(
                    state,
                    SystemStatus.PLAN_REVISING,
                    f"revision needed (round {round_num + 1}/{max_rounds})",
                )
                state.current_phase = MergePhase.PLAN_REVISING
                revised_plan = await planner.revise_plan(state, verdict.issues)
                round_log = round_log.model_copy(
                    update={
                        "planner_revision_summary": (
                            f"Revised plan with {len(verdict.issues)} issues addressed"
                        )
                    }
                )
                state.plan_review_log.append(round_log)
                state.merge_plan = revised_plan
                state.file_classifications = {
                    fp: batch.risk_level
                    for batch in revised_plan.phases
                    for fp in batch.file_paths
                }
                ctx.state_machine.transition(
                    state, SystemStatus.PLAN_REVIEWING, "revision complete"
                )
                state.current_phase = MergePhase.PLAN_REVIEW
            else:
                state.plan_review_log.append(round_log)
                phase_result = phase_result.model_copy(
                    update={"status": "completed", "completed_at": datetime.now()}
                )
                state.phase_results[MergePhase.PLAN_REVIEW.value] = phase_result
                write_plan_review_report(state, ctx.config.output.directory)
                logger.warning(
                    "Plan review did not converge after %d rounds — "
                    "proceeding with last revised plan",
                    max_rounds,
                )
                ctx.state_machine.transition(
                    state,
                    SystemStatus.AWAITING_HUMAN,
                    f"plan review did not converge after {max_rounds} rounds, "
                    f"proceeding with last plan",
                )
                return PhaseOutcome(
                    target_status=SystemStatus.AWAITING_HUMAN,
                    reason=f"plan review did not converge after {max_rounds} rounds",
                    checkpoint_tag="after_phase1_5",
                )

        return PhaseOutcome(
            target_status=state.status,
            reason="plan review loop exhausted",
            checkpoint_tag="after_phase1_5",
        )
