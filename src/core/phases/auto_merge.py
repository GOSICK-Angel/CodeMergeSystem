from __future__ import annotations

import logging
from datetime import datetime

from src.core.phases.base import Phase, PhaseContext, PhaseOutcome
from src.core.phases._gate_helpers import (
    append_execution_record,
    build_layer_index,
    get_layer_gates,
    handle_gate_failure,
    run_gates,
    verify_layer_deps,
)
from src.models.diff import FileDiff, FileChangeCategory, RiskLevel
from src.models.dispute import PlanDisputeRequest
from src.models.plan import MergePhase
from src.models.state import MergeState, PhaseResult, SystemStatus
from src.tools.commit_replayer import CommitReplayer
from src.tools.git_committer import GitCommitter

logger = logging.getLogger(__name__)


class AutoMergePhase(Phase):
    name = "auto_merge"

    async def execute(self, state: MergeState, ctx: PhaseContext) -> PhaseOutcome:
        state.current_phase = MergePhase.AUTO_MERGE
        phase_result = PhaseResult(
            phase=MergePhase.AUTO_MERGE,
            status="running",
            started_at=datetime.now(),
        )
        state.phase_results[MergePhase.AUTO_MERGE.value] = phase_result

        if state.merge_plan is None:
            raise ValueError("No merge plan available for phase 2")

        executor = ctx.agents["executor"]
        file_diffs_map: dict[str, FileDiff] = {}
        for fd in state.file_diffs:
            file_diffs_map[fd.file_path] = fd

        replayed_set: set[str] = set()
        if ctx.config.history.enabled and ctx.config.history.cherry_pick_clean:
            replayable = state.replayable_commits
            if replayable:
                replayer = CommitReplayer()
                ctx.notify(
                    "executor", f"Cherry-picking {len(replayable)} clean commits"
                )
                replay_result = await replayer.replay_clean_commits(
                    ctx.git_tool, replayable, state
                )
                replayed_set = set(replay_result.replayed_files)
                logger.info(
                    "Replay: %d commits cherry-picked, %d failed",
                    len(replay_result.replayed_shas),
                    len(replay_result.failed_shas),
                )

        batch_count = 0
        phase_changed_files: list[str] = []
        completed_layers: set[int] = set()
        layer_index = build_layer_index(state)

        for batch in state.merge_plan.phases:
            if batch.risk_level not in (RiskLevel.AUTO_SAFE, RiskLevel.DELETED_ONLY):
                continue

            if batch.layer_id is not None:
                deps_ok = verify_layer_deps(batch.layer_id, completed_layers, state)
                if not deps_ok:
                    logger.warning(
                        "Skipping batch %s (layer %d): dependencies not met",
                        batch.batch_id,
                        batch.layer_id,
                    )
                    continue

            for file_path in batch.file_paths:
                if file_path in replayed_set:
                    continue

                category = batch.change_category
                if category is None:
                    fd = file_diffs_map.get(file_path)
                    category = fd.change_category if fd else None

                if category == FileChangeCategory.D_MISSING:
                    record = await executor._copy_from_upstream(file_path, state)
                    state.file_decision_records[file_path] = record
                    phase_changed_files.append(file_path)
                    batch_count += 1
                    continue

                fd = file_diffs_map.get(file_path)
                if fd is None:
                    continue

                strategy = executor._select_strategy_by_category(
                    category, batch.risk_level
                )
                record = await executor.execute_auto_merge(fd, strategy, state)
                state.file_decision_records[file_path] = record
                phase_changed_files.append(file_path)
                batch_count += 1

                if batch_count % 10 == 0:
                    ctx.checkpoint.save(state, f"phase2_batch_{batch_count}")

            if batch.layer_id is not None and batch.layer_id not in completed_layers:
                completed_layers.add(batch.layer_id)
                layer_gates = get_layer_gates(batch.layer_id, layer_index)
                if layer_gates:
                    gate_ok = await run_gates(
                        state, ctx, f"layer_{batch.layer_id}", layer_gates
                    )
                    if not gate_ok:
                        gate_blocked = await handle_gate_failure(state, ctx)
                        if gate_blocked:
                            return PhaseOutcome(
                                target_status=SystemStatus.AWAITING_HUMAN,
                                reason="gate failure during layer merge",
                                checkpoint_tag="after_phase2",
                                memory_phase="auto_merge",
                            )

        gate_ok = await run_gates(state, ctx, "auto_merge")
        if not gate_ok:
            gate_blocked = await handle_gate_failure(state, ctx)
            if gate_blocked:
                return PhaseOutcome(
                    target_status=SystemStatus.AWAITING_HUMAN,
                    reason="gate failure after auto-merge",
                    checkpoint_tag="after_phase2",
                    memory_phase="auto_merge",
                )

        commit_sha: str | None = None
        if (
            ctx.config.history.enabled
            and ctx.config.history.commit_after_phase
            and phase_changed_files
        ):
            committer = GitCommitter()
            commit_sha = committer.commit_phase_changes(
                ctx.git_tool,
                state,
                "auto_merge",
                phase_changed_files,
            )

        has_risky = any(
            batch.risk_level in (RiskLevel.HUMAN_REQUIRED, RiskLevel.AUTO_RISKY)
            for batch in state.merge_plan.phases
        )

        phase_result = phase_result.model_copy(
            update={"status": "completed", "completed_at": datetime.now()}
        )
        state.phase_results[MergePhase.AUTO_MERGE.value] = phase_result

        append_execution_record(
            state, "auto_merge", phase_result, batch_count, commit_sha=commit_sha
        )

        if state.plan_disputes:
            ctx.state_machine.transition(
                state,
                SystemStatus.PLAN_DISPUTE_PENDING,
                "executor raised plan dispute",
            )
            await self._handle_plan_dispute(state, ctx, state.plan_disputes[-1])
            return PhaseOutcome(
                target_status=state.status,
                reason="plan dispute handled",
                checkpoint_tag="after_phase2",
                memory_phase="auto_merge",
            )
        elif has_risky:
            ctx.state_machine.transition(
                state,
                SystemStatus.ANALYZING_CONFLICTS,
                "proceeding to conflict analysis",
            )
            return PhaseOutcome(
                target_status=SystemStatus.ANALYZING_CONFLICTS,
                reason="proceeding to conflict analysis",
                checkpoint_tag="after_phase2",
                memory_phase="auto_merge",
            )
        else:
            ctx.state_machine.transition(
                state,
                SystemStatus.JUDGE_REVIEWING,
                "no risky files, skip to judge review",
            )
            return PhaseOutcome(
                target_status=SystemStatus.JUDGE_REVIEWING,
                reason="no risky files, skip to judge review",
                checkpoint_tag="after_phase2",
                memory_phase="auto_merge",
            )

    async def _handle_plan_dispute(
        self,
        state: MergeState,
        ctx: PhaseContext,
        dispute: PlanDisputeRequest,
    ) -> None:
        from src.models.diff import FileDiff
        from src.models.plan_judge import PlanJudgeResult

        planner = ctx.agents["planner"]
        planner_judge = ctx.agents["planner_judge"]

        try:
            ctx.state_machine.transition(
                state,
                SystemStatus.PLAN_REVISING,
                f"dispute: {dispute.dispute_reason}",
            )
            revised_plan = await planner.handle_dispute(state, dispute)
            state.merge_plan = revised_plan

            file_diffs: list[FileDiff] = state.file_diffs
            ctx.state_machine.transition(
                state, SystemStatus.PLAN_REVIEWING, "dispute revision complete"
            )

            verdict = await planner_judge.review_plan(
                revised_plan, file_diffs, 0, lang=ctx.config.output.language
            )
            state.plan_judge_verdict = verdict

            if verdict.result == PlanJudgeResult.APPROVED:
                dispute.resolved = True
                dispute.resolution_summary = "Plan revised and approved after dispute"
                ctx.state_machine.transition(
                    state,
                    SystemStatus.AUTO_MERGING,
                    "dispute resolved, plan approved",
                )
            else:
                ctx.state_machine.transition(
                    state,
                    SystemStatus.AWAITING_HUMAN,
                    "dispute could not be resolved automatically",
                )
        except Exception as e:
            logger.error("Plan dispute handling failed: %s", e)
            ctx.state_machine.transition(
                state,
                SystemStatus.AWAITING_HUMAN,
                f"dispute handling error: {e}",
            )
