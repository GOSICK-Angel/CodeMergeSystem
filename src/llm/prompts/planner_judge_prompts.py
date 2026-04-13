from src.models.plan import MergePlan
from src.models.diff import FileDiff


_PLANNER_JUDGE_SYSTEM_BASE = """You are an independent reviewer of code merge plans. Your task is to find
risks that may be underestimated in the plan, incorrect file classifications, missing security-sensitive files,
and batch granularity issues.
You do not know the Planner's reasoning process; you only see the final plan and the raw diff, and draw independent conclusions.
When you find issues, you must point out specific file paths and specific reasons. Vague descriptions are not allowed.
Be critical and thorough.

IMPORTANT: You MUST respond with ONLY a single JSON object. No markdown, no explanations, no text before or after the JSON.
Your entire response must be valid JSON that can be parsed by json.loads()."""

_PLANNER_JUDGE_SYSTEM_ZH_SUFFIX = """

语言要求（最高优先级）：
- "summary" 字段必须使用中文撰写。
- 每个 issue 的 "reason" 字段必须使用中文撰写。
- 禁止在这两个字段中使用英文句子，技术术语（如文件路径、枚举值）除外。"""


def get_planner_judge_system(lang: str = "en") -> str:
    if lang == "zh":
        return _PLANNER_JUDGE_SYSTEM_BASE + _PLANNER_JUDGE_SYSTEM_ZH_SUFFIX
    return _PLANNER_JUDGE_SYSTEM_BASE


def _build_file_manifest(file_diffs: list[FileDiff]) -> str:
    """Compact one-line-per-file manifest: path + classification + flags."""
    lines: list[str] = []
    for fd in file_diffs:
        flags: list[str] = []
        if fd.is_security_sensitive:
            flags.append("SEC")
        if fd.conflict_count > 0:
            flags.append(f"conflicts={fd.conflict_count}")
        if fd.lines_added + fd.lines_deleted > 100:
            flags.append(f"+{fd.lines_added}/-{fd.lines_deleted}")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"  {fd.file_path}: {fd.risk_level.value}{flag_str}")
    return "\n".join(lines)


def build_plan_review_prompt(
    plan: MergePlan, file_diffs: list[FileDiff], lang: str = "en"
) -> str:
    phases_summary = "\n".join(
        f"  Phase {batch.phase.value}: {len(batch.file_paths)} files ({batch.risk_level.value})"
        for batch in plan.phases
    )

    manifest = _build_file_manifest(file_diffs)

    return f"""Review the following merge plan for quality and correctness.

## Merge Plan Summary
- Upstream: {plan.upstream_ref}
- Fork: {plan.fork_ref}
- Total files: {plan.risk_summary.total_files}
- Auto-safe: {plan.risk_summary.auto_safe_count}
- Auto-risky: {plan.risk_summary.auto_risky_count}
- Human required: {plan.risk_summary.human_required_count}

## Phase Breakdown
{phases_summary}

## All Files (path: classification [flags])
{manifest}

## Your Review Tasks
1. Check if any security-sensitive files are incorrectly classified as auto_safe
2. Check if high-conflict files are correctly classified
3. Check if any deleted files should require human review
4. Check if batch granularity is appropriate

Return JSON with:
{{
  "result": "approved" | "revision_needed" | "critical_replan",
  "issues": [
    {{
      "file_path": "path/to/file",
      "current_classification": "<MUST be exactly one of: auto_safe, auto_risky, human_required, deleted_only, binary, excluded>",
      "suggested_classification": "<MUST be exactly one of: auto_safe, auto_risky, human_required, deleted_only, binary, excluded>",
      "reason": "Specific reason why classification is wrong",
      "issue_type": "risk_underestimated | wrong_batch | missing_dependency | security_missed"
    }}
  ],
  "approved_files_count": 0,
  "flagged_files_count": 0,
  "summary": "Overall assessment"
}}

CRITICAL: Each issue MUST reference a SINGLE file_path. The "current_classification" and "suggested_classification" fields MUST be exactly one of the enum values listed above — do NOT combine multiple values or add free text.
{"⚠️ 语言要求：'summary' 和每个 issue 的 'reason' 字段必须使用中文撰写，禁止使用英文句子（技术术语如文件路径、枚举值除外）。" if lang == "zh" else ""}
Respond with ONLY the JSON object. No other text."""
