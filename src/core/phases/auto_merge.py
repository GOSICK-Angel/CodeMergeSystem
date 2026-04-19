from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime

from src.agents.executor_agent import ExecutorAgent
from src.agents.judge_agent import JudgeAgent
from src.core.phases.base import Phase, PhaseContext, PhaseOutcome
from src.core.phases._gate_helpers import (
    append_execution_record,
    build_layer_index,
    get_layer_gates,
    handle_gate_failure,
    run_gates,
    verify_layer_deps,
)
from src.core.read_only_state_view import ReadOnlyStateView
from src.models.diff import FileDiff, FileChangeCategory, RiskLevel
from src.models.dispute import PlanDisputeRequest
from src.models.judge import BatchVerdict
from src.models.plan import MergePhase, PhaseFileBatch
from src.models.plan_review import DecisionOption, UserDecisionItem
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

        executor: ExecutorAgent = ctx.agents["executor"]
        judge: JudgeAgent = ctx.agents["judge"]
        file_diffs_map: dict[str, FileDiff] = {
            fd.file_path: fd for fd in state.file_diffs
        }

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

        # --- Pre-pass: handle HUMAN_REQUIRED and DELETED_ONLY before any merge ---
        for batch in state.merge_plan.phases:
            if batch.risk_level == RiskLevel.HUMAN_REQUIRED:
                for file_path in batch.file_paths:
                    state.pending_user_decisions.append(
                        UserDecisionItem(
                            item_id=f"human_required_{file_path}",
                            file_path=file_path,
                            description=(
                                f"File '{file_path}' requires human review "
                                f"(risk_level=HUMAN_REQUIRED)."
                            ),
                            risk_context=(
                                f"Change category: {batch.change_category}. "
                                "High risk or security-sensitive file."
                            ),
                            current_classification=RiskLevel.HUMAN_REQUIRED.value,
                            options=[
                                DecisionOption(
                                    key="A",
                                    label="approve_merge",
                                    description="Approve auto-merge attempt for this file",
                                ),
                                DecisionOption(
                                    key="B",
                                    label="keep_current",
                                    description="Keep fork version (skip upstream changes)",
                                ),
                                DecisionOption(
                                    key="C",
                                    label="take_upstream",
                                    description="Take upstream version as-is",
                                ),
                            ],
                        )
                    )
            elif batch.risk_level == RiskLevel.DELETED_ONLY:
                for file_path in batch.file_paths:
                    fd = file_diffs_map.get(file_path)
                    if fd is not None:
                        item = await executor.analyze_deletion(file_path, fd, state)
                        state.pending_user_decisions.append(item)

        if state.pending_user_decisions:
            ctx.state_machine.transition(
                state,
                SystemStatus.AWAITING_HUMAN,
                "pre-pass: HUMAN_REQUIRED or DELETED_ONLY decisions needed before merge",
            )
            return PhaseOutcome(
                target_status=SystemStatus.AWAITING_HUMAN,
                reason="pre-pass: pending human decisions before merge",
                checkpoint_tag="after_phase2_prepass",
                memory_phase="auto_merge",
            )

        # --- Main loop: layer-based, parallel within each layer ---
        batch_count = 0
        phase_changed_files: list[str] = []
        completed_layers: set[int] = set()
        layer_index = build_layer_index(state)
        max_dispute = ctx.config.max_dispute_rounds

        # Group AUTO_SAFE / AUTO_RISKY batches by layer_id (None = no layer)
        layer_batches: dict[int | None, list[PhaseFileBatch]] = defaultdict(list)
        for batch in state.merge_plan.phases:
            if batch.risk_level in (RiskLevel.AUTO_SAFE, RiskLevel.AUTO_RISKY):
                layer_batches[batch.layer_id].append(batch)

        # Sort: None-layer first (no deps), then layers in ascending order
        sorted_layer_ids: list[int | None] = []
        if None in layer_batches:
            sorted_layer_ids.append(None)
        sorted_layer_ids.extend(sorted(k for k in layer_batches if k is not None))

        for layer_id in sorted_layer_ids:
            batches = layer_batches[layer_id]

            if layer_id is not None:
                if not verify_layer_deps(layer_id, completed_layers, state):
                    logger.warning("Skipping layer %d: dependencies not met", layer_id)
                    continue

            # Parallel execution of all batches in this layer
            layer_results = await asyncio.gather(
                *[
                    self._execute_batch(
                        batch, executor, file_diffs_map, replayed_set, state
                    )
                    for batch in batches
                ],
                return_exceptions=True,
            )

            layer_files: list[str] = []
            for result in layer_results:
                if isinstance(result, Exception):
                    logger.error(
                        "Batch execution error in layer %s: %s", layer_id, result
                    )
                else:
                    files: list[str] = result  # type: ignore[assignment]
                    phase_changed_files.extend(files)
                    layer_files.extend(files)
                    batch_count += len(files)

            if batch_count % 10 == 0 and batch_count > 0:
                ctx.checkpoint.save(state, f"phase2_batch_{batch_count}")

            # Per-layer batch Judge sub-review + Executor ↔ Judge dispute loop
            if layer_files:
                readonly = ReadOnlyStateView(state)
                batch_verdict: BatchVerdict = await judge.review_batch(
                    layer_id, layer_files, readonly
                )

                for dispute_round in range(max_dispute):
                    if batch_verdict.approved:
                        break

                    rebuttal = await executor.build_rebuttal(
                        batch_verdict.issues, state
                    )

                    if rebuttal.accepts_all:
                        if rebuttal.repair_instructions:
                            await executor.repair(rebuttal.repair_instructions, state)
                        batch_verdict = await judge.review_batch(
                            layer_id, layer_files, ReadOnlyStateView(state)
                        )
                        continue

                    batch_verdict = await judge.re_evaluate(
                        rebuttal, batch_verdict, ReadOnlyStateView(state)
                    )

                if not batch_verdict.approved:
                    logger.warning(
                        "Layer %s batch judge sub-review: no consensus after %d dispute rounds",
                        layer_id,
                        max_dispute,
                    )
                    ctx.state_machine.transition(
                        state,
                        SystemStatus.AWAITING_HUMAN,
                        f"layer {layer_id} batch judge sub-review failed after "
                        f"{max_dispute} dispute rounds",
                    )
                    return PhaseOutcome(
                        target_status=SystemStatus.AWAITING_HUMAN,
                        reason=f"layer {layer_id} judge sub-review: no consensus",
                        checkpoint_tag="after_phase2",
                        memory_phase="auto_merge",
                    )

            # Layer gate checks
            if layer_id is not None:
                completed_layers.add(layer_id)
                layer_gates = get_layer_gates(layer_id, layer_index)
                if layer_gates:
                    gate_ok = await run_gates(
                        state, ctx, f"layer_{layer_id}", layer_gates
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

        has_auto_risky = any(
            batch.risk_level == RiskLevel.AUTO_RISKY
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
        elif has_auto_risky:
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

    async def _execute_batch(
        self,
        batch: PhaseFileBatch,
        executor: ExecutorAgent,
        file_diffs_map: dict[str, FileDiff],
        replayed_set: set[str],
        state: MergeState,
    ) -> list[str]:
        changed_files: list[str] = []
        for file_path in batch.file_paths:
            if file_path in replayed_set:
                continue

            category = batch.change_category
            if category is None:
                fd_lookup = file_diffs_map.get(file_path)
                category = fd_lookup.change_category if fd_lookup else None

            if category == FileChangeCategory.D_MISSING:
                record = await executor._copy_from_upstream(file_path, state)
                state.file_decision_records[file_path] = record
                changed_files.append(file_path)
                continue

            fd_item: FileDiff | None = file_diffs_map.get(file_path)
            if fd_item is None:
                continue

            strategy = executor._select_strategy_by_category(category, batch.risk_level)
            record = await executor.execute_auto_merge(fd_item, strategy, state)
            state.file_decision_records[file_path] = record
            changed_files.append(file_path)

        return changed_files

    async def _handle_plan_dispute(
        self,
        state: MergeState,
        ctx: PhaseContext,
        dispute: PlanDisputeRequest,
    ) -> None:
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
