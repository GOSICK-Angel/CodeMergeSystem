from src.models.diff import FileDiff
from src.models.plan import MergePlan
from src.models.plan_judge import PlanIssue


PLANNER_SYSTEM_TEMPLATE = """You are a code merge planning expert. Your task is to analyze differences between two branches,
classify all changed files into different risk levels, and generate a phased merge plan.
Focus on: complete coverage of all files, reasonable risk estimation, identifying critical dependencies.
Output structured JSON. Risk levels: auto_safe, auto_risky, human_required, deleted_only, binary, excluded.
{lang_instruction}"""


def get_planner_system(language: str = "en") -> str:
    if language == "en":
        return PLANNER_SYSTEM_TEMPLATE.format(lang_instruction="")
    return PLANNER_SYSTEM_TEMPLATE.format(
        lang_instruction=f"\nIMPORTANT: All text fields (project_context_summary, special_instructions, summaries, reasons) MUST be written in {language}. JSON keys remain in English."
    )


PLANNER_SYSTEM = get_planner_system("en")


def build_classification_prompt(
    file_diffs: list[FileDiff],
    project_context: str,
    batch_index: int = 0,
    total_batches: int = 1,
) -> str:
    file_list_lines: list[str] = []
    for fd in file_diffs:
        file_list_lines.append(
            f"- {fd.file_path} | status={fd.file_status.value} | "
            f"lines_added={fd.lines_added} | lines_deleted={fd.lines_deleted} | "
            f"conflicts={fd.conflict_count} | security_sensitive={fd.is_security_sensitive}"
        )

    file_list = "\n".join(file_list_lines)

    batch_hint = ""
    if total_batches > 1:
        batch_hint = f"\nNote: This is batch {batch_index + 1} of {total_batches}. Classify only the files listed below.\n"

    return f"""Analyze the following changed files and create a merge plan.

Project context:
{project_context or "No project context provided."}
{batch_hint}
Changed files ({len(file_diffs)} total):
{file_list}

Create a phased merge plan with the following structure:
1. Classify each file by risk level
2. Group files into batches by phase
3. Summarize risk distribution

Return JSON with this structure:
{{
  "phases": [
    {{
      "batch_id": "unique-id",
      "phase": "auto_merge",
      "file_paths": ["path/to/file.py"],
      "risk_level": "auto_safe",
      "can_parallelize": true
    }}
  ],
  "risk_summary": {{
    "total_files": {len(file_diffs)},
    "auto_safe_count": 0,
    "auto_risky_count": 0,
    "human_required_count": 0,
    "deleted_only_count": 0,
    "binary_count": 0,
    "excluded_count": 0,
    "estimated_auto_merge_rate": 0.0,
    "top_risk_files": []
  }},
  "project_context_summary": "Brief project summary",
  "special_instructions": []
}}"""


MAX_REVISION_ISSUES = 50


def build_revision_prompt(
    original_plan: MergePlan, judge_issues: list[PlanIssue]
) -> str:
    capped_issues = judge_issues[:MAX_REVISION_ISSUES]
    issues_text = "\n".join(
        f"- File: {issue.file_path}\n"
        f"  Current: {issue.current_classification.value}\n"
        f"  Suggested: {issue.suggested_classification.value}\n"
        f"  Reason: {issue.reason}\n"
        f"  Type: {issue.issue_type}"
        for issue in capped_issues
    )
    if len(judge_issues) > MAX_REVISION_ISSUES:
        issues_text += (
            f"\n\n(Showing {MAX_REVISION_ISSUES} of {len(judge_issues)} issues. "
            f"Apply the same reclassification pattern to similar files.)"
        )

    phases_text = "\n".join(
        f"- Batch {b.batch_id}: phase={b.phase.value}, "
        f"risk_level={b.risk_level.value}, "
        f"file_count={len(b.file_paths)}"
        for b in original_plan.phases
    )

    return f"""The plan reviewer has identified specific issues with the merge plan that need correction.

Original plan summary:
- Total files: {original_plan.risk_summary.total_files}
- Auto-safe: {original_plan.risk_summary.auto_safe_count}
- Auto-risky: {original_plan.risk_summary.auto_risky_count}
- Human required: {original_plan.risk_summary.human_required_count}

Current phases:
{phases_text}

Issues found by reviewer:
{issues_text}

Instructions:
1. For each issue, move the file from its current batch to a new or existing batch matching the suggested classification.
2. Do NOT change classifications of files not listed in the issues.
3. Recalculate risk_summary counts after reclassification.
4. Return the complete revised plan in the same JSON format as the original plan."""
