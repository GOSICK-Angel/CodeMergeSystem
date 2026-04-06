import json
from functools import partial
from pathlib import Path
from src.models.state import MergeState
from src.models.plan_review import PlanReviewRound, PlanHumanReview


_I18N: dict[str, dict[str, str]] = {
    "en": {
        "merge_report": "Merge Report",
        "status": "Status",
        "created": "Created",
        "updated": "Updated",
        "merge_plan": "Merge Plan",
        "upstream": "Upstream",
        "fork": "Fork",
        "merge_base": "Merge base",
        "risk_summary": "Risk Summary",
        "total_files": "Total files",
        "auto_safe": "Auto-safe",
        "auto_risky": "Auto-risky",
        "human_required": "Human required",
        "estimated_auto_merge_rate": "Estimated auto-merge rate",
        "file_decision_records": "File Decision Records",
        "col_file": "File",
        "col_decision": "Decision",
        "col_source": "Source",
        "col_confidence": "Confidence",
        "judge_verdict": "Judge Verdict",
        "result": "Result",
        "confidence": "Confidence",
        "summary": "Summary",
        "critical_issues": "Critical issues",
        "high_issues": "High issues",
        "errors": "Errors",
        "plan_review_report": "Plan Review Report",
        "final_plan_summary": "Final Plan Summary",
        "special_instructions": "Special Instructions",
        "phase_batches": "Phase Batches",
        "batch": "Batch",
        "files": "Files",
        "planner_judge_log": "Planner / Judge Interaction Log",
        "no_review_rounds": "No review rounds recorded.",
        "round": "Round",
        "verdict": "Verdict",
        "issues": "Issues",
        "timestamp": "Timestamp",
        "issue_details": "Issue Details",
        "planner_revision": "Planner Revision",
        "human_review": "Human Review",
        "awaiting_human": "Awaiting human review.",
        "decision": "Decision",
        "reviewer": "Reviewer",
        "notes": "Notes",
        "decided_at": "Decided at",
        "human_decision_required": "Human Decision Required",
        "files_require_review": "The following files require human review.",
        "context": "Context",
        "upstream_changes": "Upstream changes",
        "fork_changes": "Fork changes",
        "analyst_recommendation": "Analyst recommendation",
        "rationale": "Rationale",
        "options": "Options",
        "warning": "Warning",
        "priority": "priority",
    },
    "zh": {
        "merge_report": "合并报告",
        "status": "状态",
        "created": "创建时间",
        "updated": "更新时间",
        "merge_plan": "合并计划",
        "upstream": "上游分支",
        "fork": "下游分支",
        "merge_base": "合并基准",
        "risk_summary": "风险摘要",
        "total_files": "文件总数",
        "auto_safe": "自动安全",
        "auto_risky": "自动风险",
        "human_required": "需人工审核",
        "estimated_auto_merge_rate": "预计自动合并率",
        "file_decision_records": "文件决策记录",
        "col_file": "文件",
        "col_decision": "决策",
        "col_source": "来源",
        "col_confidence": "置信度",
        "judge_verdict": "审核裁决",
        "result": "结果",
        "confidence": "置信度",
        "summary": "摘要",
        "critical_issues": "严重问题",
        "high_issues": "高优问题",
        "errors": "错误",
        "plan_review_report": "计划审查报告",
        "final_plan_summary": "最终计划摘要",
        "special_instructions": "特殊说明",
        "phase_batches": "阶段批次",
        "batch": "批次",
        "files": "文件",
        "planner_judge_log": "规划器 / 审查器交互日志",
        "no_review_rounds": "暂无审查轮次记录。",
        "round": "轮次",
        "verdict": "裁决",
        "issues": "问题",
        "timestamp": "时间戳",
        "issue_details": "问题详情",
        "planner_revision": "规划器修订",
        "human_review": "人工审查",
        "awaiting_human": "等待人工审查。",
        "decision": "决策",
        "reviewer": "审查者",
        "notes": "备注",
        "decided_at": "决策时间",
        "human_decision_required": "需要人工决策",
        "files_require_review": "以下文件需要人工审查。",
        "context": "上下文",
        "upstream_changes": "上游变更",
        "fork_changes": "下游变更",
        "analyst_recommendation": "分析师建议",
        "rationale": "依据",
        "options": "选项",
        "warning": "警告",
        "priority": "优先级",
    },
}


def _t(language: str, key: str) -> str:
    return _I18N.get(language, _I18N["en"]).get(key, _I18N["en"].get(key, key))


def write_markdown_report(state: MergeState, output_dir: str) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    lang = state.config.output.language
    t = partial(_t, lang)

    report_path = output_path / f"merge_report_{state.run_id}.md"

    lines: list[str] = [
        f"# {t('merge_report')} — {state.run_id}",
        "",
        f"**{t('status')}**: {state.status.value if hasattr(state.status, 'value') else state.status}",
        f"**{t('created')}**: {state.created_at.isoformat()}",
        f"**{t('updated')}**: {state.updated_at.isoformat()}",
        "",
    ]

    if state.merge_plan:
        plan = state.merge_plan
        lines += [
            f"## {t('merge_plan')}",
            f"- {t('upstream')}: `{plan.upstream_ref}`",
            f"- {t('fork')}: `{plan.fork_ref}`",
            f"- {t('merge_base')}: `{plan.merge_base_commit}`",
            "",
            f"### {t('risk_summary')}",
            f"- {t('total_files')}: {plan.risk_summary.total_files}",
            f"- {t('auto_safe')}: {plan.risk_summary.auto_safe_count}",
            f"- {t('auto_risky')}: {plan.risk_summary.auto_risky_count}",
            f"- {t('human_required')}: {plan.risk_summary.human_required_count}",
            f"- {t('estimated_auto_merge_rate')}: {plan.risk_summary.estimated_auto_merge_rate:.1%}",
            "",
        ]

    if state.file_decision_records:
        lines += [f"## {t('file_decision_records')}", ""]
        lines += [
            f"| {t('col_file')} | {t('col_decision')} | {t('col_source')} | {t('col_confidence')} |",
            "|------|----------|--------|------------|",
        ]
        for fp, rec in state.file_decision_records.items():
            decision_val = (
                rec.decision.value if hasattr(rec.decision, "value") else rec.decision
            )
            source_val = (
                rec.decision_source.value
                if hasattr(rec.decision_source, "value")
                else rec.decision_source
            )
            conf = f"{rec.confidence:.2f}" if rec.confidence is not None else "N/A"
            lines.append(f"| `{fp}` | {decision_val} | {source_val} | {conf} |")
        lines.append("")

    if state.judge_verdict:
        verdict = state.judge_verdict
        verdict_val = (
            verdict.verdict.value
            if hasattr(verdict.verdict, "value")
            else verdict.verdict
        )
        lines += [
            f"## {t('judge_verdict')}",
            f"- **{t('result')}**: {verdict_val}",
            f"- **{t('confidence')}**: {verdict.overall_confidence:.2f}",
            f"- **{t('summary')}**: {verdict.summary}",
            f"- {t('critical_issues')}: {verdict.critical_issues_count}",
            f"- {t('high_issues')}: {verdict.high_issues_count}",
            "",
        ]

    if state.errors:
        lines += [f"## {t('errors')}", ""]
        for err in state.errors:
            lines.append(f"- `{err.get('phase', '?')}`: {err.get('message', '')}")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def write_json_report(state: MergeState, output_dir: str) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    report_path = output_path / f"merge_report_{state.run_id}.json"

    data = state.model_dump(mode="json")
    report_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return report_path


def write_human_decision_report(
    state: MergeState,
    output_dir: str,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    lang = state.config.output.language
    t = partial(_t, lang)

    report_path = output_path / f"human_decisions_{state.run_id}.md"
    lines: list[str] = [
        f"# {t('human_decision_required')} — Run {state.run_id}",
        "",
        t("files_require_review"),
        "",
    ]

    for req_id, req in state.human_decision_requests.items():
        rec_val = (
            req.analyst_recommendation.value
            if hasattr(req.analyst_recommendation, "value")
            else req.analyst_recommendation
        )
        lines += [
            f"## {req.file_path} ({t('priority')}={req.priority})",
            "",
            f"**{t('context')}**: {req.context_summary}",
            "",
            f"**{t('upstream_changes')}**: {req.upstream_change_summary}",
            "",
            f"**{t('fork_changes')}**: {req.fork_change_summary}",
            "",
            f"**{t('analyst_recommendation')}**: {rec_val} ({t('confidence')}: {req.analyst_confidence:.2f})",
            "",
            f"**{t('rationale')}**: {req.analyst_rationale}",
            "",
            f"### {t('options')}",
        ]
        for opt in req.options:
            opt_dec = (
                opt.decision.value if hasattr(opt.decision, "value") else opt.decision
            )
            lines.append(f"- **{opt.option_key}** (`{opt_dec}`): {opt.description}")
            if opt.risk_warning:
                lines.append(f"  - {t('warning')}: {opt.risk_warning}")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def write_plan_review_report(state: MergeState, output_dir: str) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    lang = state.config.output.language
    t = partial(_t, lang)

    report_path = output_path / f"plan_review_{state.run_id}.md"

    lines: list[str] = [
        f"# {t('plan_review_report')} — {state.run_id}",
        "",
        f"**{t('created')}**: {state.created_at.isoformat()}",
        "",
    ]

    if state.merge_plan:
        plan = state.merge_plan
        lines += [
            f"## {t('final_plan_summary')}",
            f"- {t('upstream')}: `{plan.upstream_ref}`",
            f"- {t('fork')}: `{plan.fork_ref}`",
            f"- {t('merge_base')}: `{plan.merge_base_commit}`",
            f"- {t('total_files')}: {plan.risk_summary.total_files}",
            f"- {t('auto_safe')}: {plan.risk_summary.auto_safe_count}",
            f"- {t('auto_risky')}: {plan.risk_summary.auto_risky_count}",
            f"- {t('human_required')}: {plan.risk_summary.human_required_count}",
            f"- {t('estimated_auto_merge_rate')}: {plan.risk_summary.estimated_auto_merge_rate:.1%}",
            "",
        ]

        if plan.special_instructions:
            lines.append(f"### {t('special_instructions')}")
            for inst in plan.special_instructions:
                lines.append(f"- {inst}")
            lines.append("")

        lines.append(f"### {t('phase_batches')}")
        for batch in plan.phases:
            risk_val = (
                batch.risk_level.value
                if hasattr(batch.risk_level, "value")
                else batch.risk_level
            )
            lines += [
                f"#### {t('batch')} `{batch.batch_id}` — {risk_val}",
                f"- {t('files')} ({len(batch.file_paths)}):",
            ]
            for fp in batch.file_paths:
                lines.append(f"  - `{fp}`")
            lines.append("")

    lines += [
        f"## {t('planner_judge_log')}",
        "",
    ]

    if not state.plan_review_log:
        lines.append(f"_{t('no_review_rounds')}_")
        lines.append("")
    else:
        for rnd in state.plan_review_log:
            result_val = (
                rnd.verdict_result.value
                if hasattr(rnd.verdict_result, "value")
                else rnd.verdict_result
            )
            lines += [
                f"### {t('round')} {rnd.round_number}",
                f"- **{t('verdict')}**: {result_val}",
                f"- **{t('summary')}**: {rnd.verdict_summary}",
                f"- **{t('issues')}**: {rnd.issues_count}",
                f"- **{t('timestamp')}**: {rnd.timestamp.isoformat()}",
            ]
            if rnd.issues_detail:
                lines.append(f"- **{t('issue_details')}**:")
                for issue in rnd.issues_detail:
                    lines.append(
                        f"  - `{issue.get('file_path', '?')}`: "
                        f"{issue.get('reason', '')} "
                        f"({issue.get('current', '?')} → {issue.get('suggested', '?')})"
                    )
            if rnd.planner_revision_summary:
                lines.append(
                    f"- **{t('planner_revision')}**: {rnd.planner_revision_summary}"
                )
            lines.append("")

    lines += [
        f"## {t('human_review')}",
        "",
    ]

    if state.plan_human_review is None:
        lines.append(f"_{t('awaiting_human')}_")
        lines.append("")
    else:
        review = state.plan_human_review
        decision_val = (
            review.decision.value
            if hasattr(review.decision, "value")
            else review.decision
        )
        lines += [
            f"- **{t('decision')}**: {decision_val}",
            f"- **{t('reviewer')}**: {review.reviewer_name or 'N/A'}",
            f"- **{t('notes')}**: {review.reviewer_notes or 'N/A'}",
            f"- **{t('decided_at')}**: {review.decided_at.isoformat()}",
            "",
        ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
