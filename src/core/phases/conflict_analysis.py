from __future__ import annotations

import logging
from datetime import datetime

from src.agents.base_agent import CIRCUIT_BREAKER_THRESHOLD
from src.core.phases.base import Phase, PhaseContext, PhaseOutcome
from src.models.conflict import ConflictAnalysis, ConflictType
from src.models.config import ThresholdConfig
from src.models.decision import MergeDecision
from src.models.diff import FileDiff
from src.models.human import HumanDecisionRequest, DecisionOption
from src.models.plan import MergePhase
from src.models.state import MergeState, PhaseResult, SystemStatus
from src.tools.commit_replayer import CommitReplayer
from src.tools.git_committer import GitCommitter
from src.tools.rule_resolver import RuleBasedResolver

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

        file_diffs_map: dict[str, FileDiff] = {}
        for fd in state.file_diffs:
            file_diffs_map[fd.file_path] = fd

        high_risk_files: list[str] = []
        if state.merge_plan:
            from src.models.diff import RiskLevel as _RL

            for batch in state.merge_plan.phases:
                if batch.risk_level in (_RL.HUMAN_REQUIRED, _RL.AUTO_RISKY):
                    high_risk_files.extend(batch.file_paths)

        rule_resolver = RuleBasedResolver()
        rule_resolved_files: set[str] = set()
        for file_path in high_risk_files:
            fd = file_diffs_map.get(file_path)
            if fd is None:
                continue
            base_c = target_c = current_c = None
            if ctx.git_tool:
                base_c, current_c, target_c = ctx.git_tool.get_three_way_diff(
                    state.merge_base_commit,
                    state.config.fork_ref,
                    state.config.upstream_ref,
                    file_path,
                )
            rule_result = rule_resolver.try_resolve(base_c, current_c, target_c)
            if rule_result.resolved and rule_result.pattern is not None:
                pattern_name = rule_result.pattern.value
                rule_resolved_files.add(file_path)
                state.conflict_analyses[file_path] = ConflictAnalysis(
                    file_path=file_path,
                    conflict_points=[],
                    overall_confidence=rule_result.confidence,
                    recommended_strategy=MergeDecision.TAKE_TARGET,
                    conflict_type=ConflictType.SEMANTIC_EQUIVALENT,
                    rationale=(
                        f"Rule-based resolution ({pattern_name}): "
                        f"{rule_result.description}"
                    ),
                    confidence=rule_result.confidence,
                )
                ctx.notify(
                    "conflict_analyst",
                    f"Rule-resolved {file_path} ({pattern_name})",
                )

        llm_files = [fp for fp in high_risk_files if fp not in rule_resolved_files]
        if rule_resolved_files:
            logger.info(
                "Rule-based resolver handled %d/%d files, %d remain for LLM",
                len(rule_resolved_files),
                len(high_risk_files),
                len(llm_files),
            )

        total = len(llm_files)
        circuit_breaker_open = False
        for idx, file_path in enumerate(llm_files, 1):
            fd = file_diffs_map.get(file_path)
            if fd is None:
                continue

            if circuit_breaker_open:
                logger.warning(
                    "Circuit breaker open — skipping LLM analysis for %s, "
                    "escalating to human",
                    file_path,
                )
                state.conflict_analyses[file_path] = ConflictAnalysis(
                    file_path=file_path,
                    conflict_points=[],
                    overall_confidence=0.0,
                    recommended_strategy=MergeDecision.ESCALATE_HUMAN,
                    conflict_type=ConflictType.UNKNOWN,
                    rationale="LLM analysis skipped — circuit breaker open, "
                    "please check API key and connectivity",
                    confidence=0.0,
                )
                continue

            ctx.notify(
                "conflict_analyst",
                f"Analyzing {file_path} ({idx}/{total})",
            )

            base_content = target_content = current_content = None
            if conflict_analyst.git_tool and hasattr(state, "_merge_base"):
                base_content, current_content, target_content = (
                    conflict_analyst.git_tool.get_three_way_diff(
                        state._merge_base or "",
                        state.config.fork_ref,
                        state.config.upstream_ref,
                        file_path,
                    )
                )

            analysis = await conflict_analyst.analyze_file(
                fd,
                base_content=base_content,
                current_content=current_content,
                target_content=target_content,
                project_context=state.config.project_context,
            )
            state.conflict_analyses[file_path] = analysis

            ctx.notify(
                "conflict_analyst",
                f"Analyzed {file_path} ({idx}/{total}) — "
                f"confidence={analysis.confidence:.0%}",
            )

            if (
                not circuit_breaker_open
                and conflict_analyst.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD
            ):
                circuit_breaker_open = True

        needs_human: list[str] = []
        decided = 0
        for file_path, analysis in state.conflict_analyses.items():
            fd = file_diffs_map.get(file_path)
            if fd is None:
                continue

            strategy = _select_merge_strategy(analysis, state.config.thresholds)
            decided += 1

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

            ctx.notify(
                "conflict_analyst",
                f"Strategy decided ({decided}/{total}): {file_path} → {strategy.value}",
            )

        if ctx.config.history.enabled and ctx.config.history.commit_after_phase:
            resolved_files = [
                fp
                for fp in state.conflict_analyses
                if fp in state.file_decision_records
                and not state.file_decision_records[fp].is_rolled_back
                and fp not in needs_human
            ]
            if resolved_files:
                committer = GitCommitter()
                replayer = CommitReplayer()
                upstream_ctx = replayer.collect_upstream_messages(
                    ctx.git_tool,
                    state.merge_base_commit,
                    state.config.upstream_ref,
                    resolved_files,
                )
                committer.commit_phase_changes(
                    ctx.git_tool,
                    state,
                    "conflict_resolution",
                    resolved_files,
                    upstream_context=upstream_ctx,
                )

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
