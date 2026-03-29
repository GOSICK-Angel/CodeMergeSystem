from __future__ import annotations

import re

from src.integrations.github_client import ReviewComment
from src.models.decision import MergeDecision
from src.models.human import HumanDecisionRequest


def format_decision_request_as_comment(
    req: HumanDecisionRequest,
) -> ReviewComment:
    """Format a HumanDecisionRequest as a GitHub PR review comment."""
    rec_val = (
        req.analyst_recommendation.value
        if hasattr(req.analyst_recommendation, "value")
        else req.analyst_recommendation
    )

    options_text = "\n".join(
        f"- `/{opt.decision.value if hasattr(opt.decision, 'value') else opt.decision}` — {opt.description}"
        for opt in req.options
    )

    body = (
        f"### Merge Decision Required\n\n"
        f"**Priority**: {req.priority}/10\n"
        f"**Context**: {req.context_summary}\n\n"
        f"**Upstream changes**: {req.upstream_change_summary}\n"
        f"**Fork changes**: {req.fork_change_summary}\n\n"
        f"**Analyst recommendation**: `{rec_val}` "
        f"(confidence: {req.analyst_confidence:.0%})\n"
        f"**Rationale**: {req.analyst_rationale}\n\n"
        f"**Available decisions:**\n{options_text}\n\n"
        f"_Reply with one of the `/command` options above to decide._"
    )

    return ReviewComment(path=req.file_path, body=body)


def format_summary_comment(
    requests: list[HumanDecisionRequest],
) -> str:
    """Format a summary comment for all pending decisions."""
    lines = [
        "## CodeMergeSystem — Human Review Required\n",
        f"**{len(requests)} files** need human decisions.\n",
        "| File | Priority | Recommendation | Confidence |",
        "|------|----------|----------------|------------|",
    ]
    for req in sorted(requests, key=lambda r: r.priority):
        rec_val = (
            req.analyst_recommendation.value
            if hasattr(req.analyst_recommendation, "value")
            else req.analyst_recommendation
        )
        lines.append(
            f"| `{req.file_path}` | {req.priority}"
            f" | {rec_val} | {req.analyst_confidence:.0%} |"
        )

    lines.append(
        "\nReview each file's inline comment and reply with a `/command` to decide."
    )
    return "\n".join(lines)


_DECISION_PATTERN = re.compile(
    r"^/(" + "|".join(d.value for d in MergeDecision) + r")\s*$",
    re.MULTILINE,
)


def parse_decision_from_comment(body: str) -> MergeDecision | None:
    """Parse a merge decision from a comment body."""
    match = _DECISION_PATTERN.search(body)
    if match:
        try:
            return MergeDecision(match.group(1))
        except ValueError:
            return None
    return None
