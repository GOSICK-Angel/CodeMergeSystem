import json
from typing import Any

from src.models.state import MergeState, SystemStatus
from src.models.judge import VerdictType


def build_ci_summary(state: MergeState) -> dict[str, Any]:
    """Build a machine-readable CI summary from merge state."""
    status_map: dict[SystemStatus, str] = {
        SystemStatus.COMPLETED: "success",
        SystemStatus.AWAITING_HUMAN: "needs_human",
        SystemStatus.FAILED: "failed",
    }
    status = status_map.get(state.status, "unknown")

    total_files = 0
    if state.merge_plan and state.merge_plan.risk_summary:
        total_files = state.merge_plan.risk_summary.total_files

    auto_merged = sum(
        1
        for rec in state.file_decision_records.values()
        if rec.decision_source.value in ("auto_planner", "auto_executor")
    )
    human_required = sum(
        1
        for req in state.human_decision_requests.values()
        if req.human_decision is None
    )
    human_decided = sum(
        1
        for req in state.human_decision_requests.values()
        if req.human_decision is not None
    )
    failed = len(state.errors)

    judge_verdict = "none"
    if state.judge_verdict is not None:
        jv = state.judge_verdict.verdict
        if isinstance(jv, VerdictType):
            judge_verdict = jv.value
        else:
            judge_verdict = str(jv)

    if status == "success" and failed > 0:
        status = "partial_failure"

    return {
        "status": status,
        "run_id": state.run_id,
        "total_files": total_files,
        "auto_merged": auto_merged,
        "human_required": human_required,
        "human_decided": human_decided,
        "failed_count": failed,
        "judge_verdict": judge_verdict,
        "errors": [err.get("message", "") for err in state.errors[-5:]],
    }


def format_ci_summary(summary: dict[str, Any]) -> str:
    """Format CI summary as JSON string."""
    return json.dumps(summary, indent=2, default=str)
