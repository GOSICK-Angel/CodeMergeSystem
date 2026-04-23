from __future__ import annotations

import logging

from src.cli.paths import get_report_dir
from src.core.phases.base import Phase, PhaseContext, PhaseOutcome
from src.models.plan import MergePhase
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

        # O-6: if conflict decisions are still pending, go to Case 1 first.
        _has_pending_conflict_decisions = bool(
            state.human_decision_requests
            and any(
                r.human_decision is None for r in state.human_decision_requests.values()
            )
        )

        # Case 0: judge review already ran and paused for human acknowledgement.
        # If the user set `state.judge_resolution` via the CLI (resume
        # --decisions), route accordingly so --no-tui users are not deadlocked.
        if (
            not _has_pending_conflict_decisions
            and state.judge_verdict is not None
            and state.current_phase == MergePhase.JUDGE_REVIEW
            and state.judge_resolution is not None
        ):
            res = state.judge_resolution
            if res == "accept":
                ctx.state_machine.transition(
                    state,
                    SystemStatus.GENERATING_REPORT,
                    "user accepted judge verdict (report only)",
                )
                return PhaseOutcome(
                    target_status=SystemStatus.GENERATING_REPORT,
                    reason="user accepted judge verdict",
                    checkpoint_tag="judge_accepted",
                )
            if res == "abort":
                ctx.state_machine.transition(
                    state,
                    SystemStatus.FAILED,
                    "user aborted after judge FAIL",
                )
                return PhaseOutcome(
                    target_status=SystemStatus.FAILED,
                    reason="user aborted after judge FAIL",
                    checkpoint_tag="judge_aborted",
                )
            if res == "rerun":
                # Clear resolution so next pause requires fresh input
                state.judge_resolution = None
                ctx.state_machine.transition(
                    state,
                    SystemStatus.AUTO_MERGING,
                    "user requested rerun of auto-merge after judge FAIL",
                )
                return PhaseOutcome(
                    target_status=SystemStatus.AUTO_MERGING,
                    reason="user requested rerun",
                    checkpoint_tag="judge_rerun",
                )

        # Guard against O-L1 loop: once judge_review has produced a verdict and
        # is paused for human adjudication, all conflict human_decision_requests
        # are already resolved & executed. Falling into Case 1's "not pending"
        # branch would re-transition to JUDGE_REVIEWING and loop indefinitely.
        if (
            state.judge_verdict is not None
            and state.current_phase == MergePhase.JUDGE_REVIEW
            and state.judge_resolution is None
        ):
            logger.info(
                "judge_review pending human resolution — staying in AWAITING_HUMAN"
            )
            return PhaseOutcome(
                target_status=SystemStatus.AWAITING_HUMAN,
                reason="judge verdict requires human resolution (accept/rerun/abort)",
                checkpoint_tag="judge_resolution_required",
                extra={"paused": True},
            )

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
