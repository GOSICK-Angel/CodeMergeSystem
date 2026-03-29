from __future__ import annotations

import logging
from typing import Any

from src.models.decision import MergeDecision
from src.models.state import MergeState
from src.tools.ci_reporter import build_ci_summary

logger = logging.getLogger(__name__)


class WebApp:
    """Lightweight web application for merge decision UI."""

    def __init__(self, state: MergeState) -> None:
        self._state = state

    def get_status(self) -> dict[str, Any]:
        """GET /api/status"""
        summary = build_ci_summary(self._state)
        summary["current_phase"] = (
            self._state.current_phase.value
            if hasattr(self._state.current_phase, "value")
            else str(self._state.current_phase)
        )
        return summary

    def get_files(self) -> list[dict[str, Any]]:
        """GET /api/files — list pending decision files"""
        files: list[dict[str, Any]] = []
        for file_path, req in self._state.human_decision_requests.items():
            rec_val = (
                req.analyst_recommendation.value
                if hasattr(req.analyst_recommendation, "value")
                else req.analyst_recommendation
            )
            files.append(
                {
                    "file_path": file_path,
                    "priority": req.priority,
                    "analyst_recommendation": rec_val,
                    "analyst_confidence": req.analyst_confidence,
                    "context_summary": req.context_summary,
                    "decided": req.human_decision is not None,
                    "decision": (
                        req.human_decision.value
                        if req.human_decision and hasattr(req.human_decision, "value")
                        else req.human_decision
                    ),
                }
            )
        return sorted(files, key=lambda f: f["priority"])

    def get_file_detail(self, file_path: str) -> dict[str, Any] | None:
        """GET /api/files/{path}"""
        req = self._state.human_decision_requests.get(file_path)
        if req is None:
            return None

        rec_val = (
            req.analyst_recommendation.value
            if hasattr(req.analyst_recommendation, "value")
            else req.analyst_recommendation
        )

        options: list[dict[str, Any]] = []
        for opt in req.options:
            opt_dec = (
                opt.decision.value if hasattr(opt.decision, "value") else opt.decision
            )
            options.append(
                {
                    "key": opt.option_key,
                    "decision": opt_dec,
                    "description": opt.description,
                    "risk_warning": opt.risk_warning,
                }
            )

        return {
            "file_path": req.file_path,
            "priority": req.priority,
            "context_summary": req.context_summary,
            "upstream_change_summary": req.upstream_change_summary,
            "fork_change_summary": req.fork_change_summary,
            "analyst_recommendation": rec_val,
            "analyst_confidence": req.analyst_confidence,
            "analyst_rationale": req.analyst_rationale,
            "options": options,
            "conflict_points": [
                cp.model_dump(mode="json") for cp in req.conflict_points
            ],
            "decided": req.human_decision is not None,
            "decision": (
                req.human_decision.value
                if req.human_decision and hasattr(req.human_decision, "value")
                else req.human_decision
            ),
        }

    def submit_decision(
        self,
        file_path: str,
        decision: str,
        reviewer_name: str | None = None,
        reviewer_notes: str | None = None,
        custom_content: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/decisions"""
        from datetime import datetime

        req = self._state.human_decision_requests.get(file_path)
        if req is None:
            return {"error": f"File not found: {file_path}", "success": False}

        try:
            merge_decision = MergeDecision(decision)
        except ValueError:
            return {"error": f"Invalid decision: {decision}", "success": False}

        if merge_decision == MergeDecision.MANUAL_PATCH and not custom_content:
            return {
                "error": "MANUAL_PATCH requires custom_content",
                "success": False,
            }

        if merge_decision == MergeDecision.ESCALATE_HUMAN:
            return {
                "error": "ESCALATE_HUMAN cannot be used as a decision",
                "success": False,
            }

        updated = req.model_copy(
            update={
                "human_decision": merge_decision,
                "custom_content": custom_content,
                "reviewer_name": reviewer_name,
                "reviewer_notes": reviewer_notes,
                "decided_at": datetime.now(),
            }
        )
        self._state.human_decision_requests[file_path] = updated
        self._state.human_decisions[file_path] = merge_decision

        return {"success": True, "file_path": file_path, "decision": decision}

    def submit_batch_decisions(
        self,
        file_paths: list[str],
        decision: str,
        reviewer_name: str | None = None,
        reviewer_notes: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/decisions/batch"""
        results: list[dict[str, Any]] = []
        for fp in file_paths:
            result = self.submit_decision(fp, decision, reviewer_name, reviewer_notes)
            results.append(result)

        succeeded = sum(1 for r in results if r.get("success"))
        return {
            "success": succeeded == len(file_paths),
            "total": len(file_paths),
            "succeeded": succeeded,
            "results": results,
        }

    def get_report(self) -> dict[str, Any]:
        """GET /api/report"""
        return build_ci_summary(self._state)

    def all_decisions_complete(self) -> bool:
        """Check if all pending decisions have been made."""
        return all(
            req.human_decision is not None
            for req in self._state.human_decision_requests.values()
        )
