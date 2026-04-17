from __future__ import annotations

import logging

from src.cli.paths import get_report_dir
from src.core.phases.base import Phase, PhaseContext, PhaseOutcome
from src.models.plan_review import PlanHumanDecision
from src.models.state import MergeState, SystemStatus
from src.tools.merge_plan_report import write_merge_plan_report
from src.tools.report_writer import write_plan_review_report
from src.tools.commit_replayer import CommitReplayer
from src.tools.git_committer import GitCommitter

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

        # Case 1: waiting for file-level conflict decisions from conflict analysis
        if state.human_decision_requests:
            pending = [
                req
                for req in state.human_decision_requests.values()
                if req.human_decision is None
            ]
            if not pending:
                executor = ctx.agents["executor"]
                executed = 0
                for req in state.human_decision_requests.values():
                    if req.file_path in state.file_decision_records:
                        continue
                    try:
                        record = await executor.execute_human_decision(req, state)
                        state.file_decision_records[req.file_path] = record
                        executed += 1
                    except Exception as e:
                        logger.error(
                            "Failed to execute human decision for %s: %s",
                            req.file_path,
                            e,
                        )
                logger.info(
                    "Executed %d human decisions — proceeding to judge review",
                    executed,
                )

                if ctx.config.history.enabled and ctx.config.history.commit_after_phase:
                    human_files = [
                        req.file_path
                        for req in state.human_decision_requests.values()
                        if req.file_path in state.file_decision_records
                        and not state.file_decision_records[
                            req.file_path
                        ].is_rolled_back
                    ]
                    if human_files:
                        committer = GitCommitter()
                        replayer = CommitReplayer()
                        upstream_ctx = replayer.collect_upstream_messages(
                            ctx.git_tool,
                            state.merge_base_commit,
                            state.config.upstream_ref,
                            human_files,
                        )
                        committer.commit_phase_changes(
                            ctx.git_tool,
                            state,
                            "human_review",
                            human_files,
                            upstream_context=upstream_ctx,
                        )

                ctx.state_machine.transition(
                    state,
                    SystemStatus.JUDGE_REVIEWING,
                    "all human conflict decisions complete",
                )
                return PhaseOutcome(
                    target_status=SystemStatus.JUDGE_REVIEWING,
                    reason="all human conflict decisions complete",
                    checkpoint_tag="after_human_decisions",
                    memory_phase="conflict_analysis",
                )
            logger.info(
                "%d/%d conflict decisions still pending",
                len(pending),
                len(state.human_decision_requests),
            )
            return PhaseOutcome(
                target_status=SystemStatus.AWAITING_HUMAN,
                reason=f"{len(pending)} conflict decisions pending",
                checkpoint_tag="awaiting_human",
                extra={"paused": True},
            )

        # Case 2: waiting for plan human review
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
            write_plan_review_report(
                state,
                str(
                    get_report_dir(
                        state.config.repo_path,
                        state.run_id,
                        ctx.config.output.directory,
                    )
                ),
            )
            if state.plan_human_review.decision == PlanHumanDecision.APPROVE:
                ctx.state_machine.transition(
                    state,
                    SystemStatus.AUTO_MERGING,
                    "plan approved by human reviewer",
                )
                return PhaseOutcome(
                    target_status=SystemStatus.AUTO_MERGING,
                    reason="plan approved by human reviewer",
                    checkpoint_tag="plan_approved",
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
                    checkpoint_tag="plan_rejected",
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
