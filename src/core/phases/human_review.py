from __future__ import annotations

import logging

from src.core.phases.base import Phase, PhaseContext, PhaseOutcome
from src.models.plan_review import PlanHumanDecision
from src.models.state import MergeState, SystemStatus
from src.tools.merge_plan_report import write_merge_plan_report
from src.tools.report_writer import write_plan_review_report

logger = logging.getLogger(__name__)


class HumanReviewPhase(Phase):
    """Handles the AWAITING_HUMAN state.

    This phase either:
    - Generates a plan report and pauses (returns early)
    - Routes a human decision (approve/reject) to the next state
    """

    name = "human_review"

    async def execute(self, state: MergeState, ctx: PhaseContext) -> PhaseOutcome:
        logger.info("Entering AWAITING_HUMAN status")

        if state.plan_human_review is None and state.merge_plan:
            ctx.notify("orchestrator", "Generating merge plan report")
            report_path = write_merge_plan_report(state)
            state.messages.append(
                {
                    "type": "plan_report",
                    "from": "orchestrator",
                    "to": "human",
                    "content": str(report_path),
                }
            )
            ctx.notify("orchestrator", f"Plan report: {report_path}")

        if state.plan_human_review is not None:
            write_plan_review_report(state, ctx.config.output.directory)
            if state.plan_human_review.decision == PlanHumanDecision.APPROVE:
                ctx.state_machine.transition(
                    state,
                    SystemStatus.AUTO_MERGING,
                    "plan approved by human reviewer",
                )
                return PhaseOutcome(
                    target_status=SystemStatus.AUTO_MERGING,
                    reason="plan approved by human reviewer",
                )
            elif state.plan_human_review.decision == PlanHumanDecision.REJECT:
                ctx.state_machine.transition(
                    state,
                    SystemStatus.FAILED,
                    "plan rejected by human reviewer",
                )
                return PhaseOutcome(
                    target_status=SystemStatus.FAILED,
                    reason="plan rejected by human reviewer",
                )
            else:
                return PhaseOutcome(
                    target_status=SystemStatus.AWAITING_HUMAN,
                    reason="awaiting human decision (modify)",
                    checkpoint_tag="awaiting_human",
                    extra={"paused": True},
                )
        else:
            return PhaseOutcome(
                target_status=SystemStatus.AWAITING_HUMAN,
                reason="awaiting human decision",
                checkpoint_tag="awaiting_human",
                extra={"paused": True},
            )
