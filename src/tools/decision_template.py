from typing import Any

import yaml
from pathlib import Path

from src.models.human import HumanDecisionRequest


def generate_decision_template(requests: list[HumanDecisionRequest]) -> str:
    """Generate an annotatable YAML decision template for human review."""
    template: dict[str, Any] = {
        "instructions": (
            "Fill in the 'decision' field for each file. "
            "Valid values: take_current, take_target, semantic_merge, manual_patch, skip. "
            "For manual_patch, also provide 'custom_content'. "
            "Leave 'decision' empty to skip a file."
        ),
        "decisions": [],
    }

    for req in requests:
        rec_val = (
            req.analyst_recommendation.value
            if hasattr(req.analyst_recommendation, "value")
            else req.analyst_recommendation
        )
        options_list: list[dict[str, Any]] = []
        for opt in req.options:
            opt_dec = (
                opt.decision.value if hasattr(opt.decision, "value") else opt.decision
            )
            options_list.append(
                {
                    "key": opt.option_key,
                    "decision": opt_dec,
                    "description": opt.description,
                }
            )

        entry: dict[str, Any] = {
            "file_path": req.file_path,
            "priority": req.priority,
            "risk_summary": req.context_summary,
            "upstream_changes": req.upstream_change_summary,
            "fork_changes": req.fork_change_summary,
            "analyst_recommendation": rec_val,
            "analyst_confidence": round(req.analyst_confidence, 2),
            "analyst_rationale": req.analyst_rationale,
            "options": options_list,
            "decision": "",
            "custom_content": None,
            "reviewer_name": "",
            "reviewer_notes": "",
        }
        template["decisions"].append(entry)

    return yaml.dump(
        template,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def export_decision_template(
    requests: list[HumanDecisionRequest], output_path: str
) -> str:
    """Export decision template to a YAML file."""
    content = generate_decision_template(requests)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)
