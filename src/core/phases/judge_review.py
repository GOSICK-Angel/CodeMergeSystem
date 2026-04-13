from __future__ import annotations

import logging
from datetime import datetime

from src.core.phases.base import Phase, PhaseContext, PhaseOutcome
from src.core.phases._gate_helpers import (
    append_judge_record,
    handle_gate_failure,
    run_gates,
)
from src.core.read_only_state_view import ReadOnlyStateView
from src.models.judge import VerdictType
from src.models.plan import MergePhase
from src.models.state import MergeState, PhaseResult, SystemStatus

logger = logging.getLogger(__name__)


class JudgeReviewPhase(Phase):
    name = "judge_review"

    async def execute(self, state: MergeState, ctx: PhaseContext) -> PhaseOutcome:
        state.current_phase = MergePhase.JUDGE_REVIEW
        phase_result = PhaseResult(
            phase=MergePhase.JUDGE_REVIEW,
            status="running",
            started_at=datetime.now(),
        )
        state.phase_results[MergePhase.JUDGE_REVIEW.value] = phase_result

        judge = ctx.agents["judge"]
        executor = ctx.agents["executor"]
        max_rounds = ctx.config.max_judge_repair_rounds
        state.judge_repair_rounds = 0

        for round_num in range(max_rounds):
            state.judge_repair_rounds = round_num

            readonly = ReadOnlyStateView(state)
            msg = await judge.run(readonly)
            verdict_data = msg.payload.get("verdict")
            if verdict_data:
                from src.models.judge import JudgeVerdict as JV

                state.judge_verdict = JV.model_validate(verdict_data)

            customization_violations = judge.verify_customizations(
                ctx.config.customizations
            )
            if state.judge_verdict and customization_violations:
                state.judge_verdict = state.judge_verdict.model_copy(
                    update={
                        "customization_violations": customization_violations,
                        "veto_triggered": True,
                        "veto_reason": (
                            "Customization(s) lost: "
                            f"{', '.join(v.customization_name for v in customization_violations)}"
                        ),
                        "verdict": VerdictType.FAIL,
                    }
                )

            state.judge_verdicts_log.append(
                {
                    "round": round_num,
                    "verdict": state.judge_verdict.verdict.value
                    if state.judge_verdict
                    else "none",
                    "timestamp": datetime.now().isoformat(),
                    "issues_count": len(state.judge_verdict.issues)
                    if state.judge_verdict
                    else 0,
                    "veto": state.judge_verdict.veto_triggered
                    if state.judge_verdict
                    else False,
                }
            )

            append_judge_record(state, round_num)

            if state.judge_verdict is None:
                break

            if state.judge_verdict.verdict == VerdictType.PASS:
                logger.info("Judge PASS on round %d", round_num)
                break

            if state.judge_verdict.veto_triggered:
                logger.warning(
                    "Judge VETO on round %d: %s",
                    round_num,
                    state.judge_verdict.veto_reason,
                )
                break

            repair_instructions = judge.build_repair_instructions(
                state.judge_verdict.issues
            )
            state.judge_verdict = state.judge_verdict.model_copy(
                update={"repair_instructions": repair_instructions}
            )

            repairable = [r for r in repair_instructions if r.is_repairable]
            if not repairable:
                logger.info("No repairable issues on round %d, escalating", round_num)
                break

            if round_num < max_rounds - 1:
                logger.info(
                    "Repair round %d/%d: %d instructions",
                    round_num + 1,
                    max_rounds,
                    len(repairable),
                )
                await executor.repair(repairable, state)
                ctx.checkpoint.save(state, f"phase5_repair_{round_num}")

        phase_result = phase_result.model_copy(
            update={"status": "completed", "completed_at": datetime.now()}
        )
        state.phase_results[MergePhase.JUDGE_REVIEW.value] = phase_result

        gate_ok = await run_gates(state, ctx, "judge_review")
        if not gate_ok:
            gate_blocked = await handle_gate_failure(state, ctx)
            if gate_blocked:
                return PhaseOutcome(
                    target_status=SystemStatus.AWAITING_HUMAN,
                    reason="gate failure after judge review",
                    checkpoint_tag="after_phase5",
                    memory_phase="judge_review",
                )

        if state.judge_verdict is None:
            ctx.state_machine.transition(
                state,
                SystemStatus.GENERATING_REPORT,
                "judge review complete (no verdict)",
            )
            return PhaseOutcome(
                target_status=SystemStatus.GENERATING_REPORT,
                reason="judge review complete (no verdict)",
                checkpoint_tag="after_phase5",
                memory_phase="judge_review",
            )

        verdict_type = state.judge_verdict.verdict
        if verdict_type == VerdictType.PASS:
            ctx.state_machine.transition(
                state, SystemStatus.GENERATING_REPORT, "judge verdict: PASS"
            )
            target = SystemStatus.GENERATING_REPORT
            reason = "judge verdict: PASS"
        elif state.judge_verdict.veto_triggered:
            ctx.state_machine.transition(
                state,
                SystemStatus.AWAITING_HUMAN,
                f"judge VETO: {state.judge_verdict.veto_reason}",
            )
            target = SystemStatus.AWAITING_HUMAN
            reason = f"judge VETO: {state.judge_verdict.veto_reason}"
        elif verdict_type == VerdictType.CONDITIONAL:
            ctx.state_machine.transition(
                state, SystemStatus.AWAITING_HUMAN, "judge verdict: CONDITIONAL"
            )
            target = SystemStatus.AWAITING_HUMAN
            reason = "judge verdict: CONDITIONAL"
        else:
            ctx.state_machine.transition(
                state,
                SystemStatus.AWAITING_HUMAN,
                f"judge verdict: FAIL after {state.judge_repair_rounds + 1} rounds",
            )
            target = SystemStatus.AWAITING_HUMAN
            reason = f"judge verdict: FAIL after {state.judge_repair_rounds + 1} rounds"

        return PhaseOutcome(
            target_status=target,
            reason=reason,
            checkpoint_tag="after_phase5",
            memory_phase="judge_review",
        )
