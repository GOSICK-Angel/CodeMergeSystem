from src.models.diff import FileDiff


RISK_SCORING_SYSTEM = (
    "You are a code risk assessment specialist. "
    "Analyze the given file diff and provide a risk score."
)


def build_risk_scoring_prompt(file_diff: FileDiff, rule_score: float) -> str:
    ext = (
        file_diff.file_path.rsplit(".", 1)[-1]
        if "." in file_diff.file_path
        else "unknown"
    )

    hunk_summaries = []
    for h in file_diff.hunks[:10]:
        hunk_summaries.append(
            f"  - Lines {h.start_line_current}-{h.end_line_current}: "
            f"conflict={'yes' if h.has_conflict else 'no'}"
        )
    hunks_text = "\n".join(hunk_summaries) if hunk_summaries else "  (no hunks)"

    return f"""Analyze the risk of merging changes to this file.

File: {file_diff.file_path}
Extension: .{ext}
Lines added: {file_diff.lines_added}
Lines deleted: {file_diff.lines_deleted}
Lines changed: {file_diff.lines_changed}
Security sensitive: {file_diff.is_security_sensitive}
Rule-based risk score: {rule_score:.3f}

Hunks:
{hunks_text}

Respond with ONLY a JSON object:
{{
  "llm_risk_score": <float between 0.0 and 1.0>,
  "reasoning": "<brief explanation>",
  "risk_factors": ["<factor1>", "<factor2>"]
}}"""
