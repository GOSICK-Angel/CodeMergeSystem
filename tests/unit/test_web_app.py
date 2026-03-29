import pytest
from datetime import datetime

from src.models.config import MergeConfig
from src.models.decision import MergeDecision
from src.models.human import DecisionOption, HumanDecisionRequest
from src.models.state import MergeState, SystemStatus
from src.web.app import WebApp


def _make_config() -> MergeConfig:
    return MergeConfig(upstream_ref="upstream/main", fork_ref="fork/main")


def _make_request(file_path: str = "src/main.py") -> HumanDecisionRequest:
    return HumanDecisionRequest(
        file_path=file_path,
        priority=5,
        conflict_points=[],
        context_summary="File has conflicts",
        upstream_change_summary="Added 10 lines",
        fork_change_summary="Deleted 5 lines",
        analyst_recommendation=MergeDecision.TAKE_TARGET,
        analyst_confidence=0.75,
        analyst_rationale="Upstream preferred",
        options=[
            DecisionOption(
                option_key="A",
                decision=MergeDecision.TAKE_CURRENT,
                description="Keep fork",
            ),
            DecisionOption(
                option_key="B",
                decision=MergeDecision.TAKE_TARGET,
                description="Take upstream",
            ),
        ],
        created_at=datetime.now(),
    )


class TestWebApp:
    def test_get_status(self) -> None:
        state = MergeState(config=_make_config())
        state.status = SystemStatus.AWAITING_HUMAN
        app = WebApp(state)
        status = app.get_status()
        assert status["status"] == "needs_human"

    def test_get_files_empty(self) -> None:
        state = MergeState(config=_make_config())
        app = WebApp(state)
        assert app.get_files() == []

    def test_get_files_with_requests(self) -> None:
        state = MergeState(config=_make_config())
        req = _make_request("a.py")
        state.human_decision_requests["a.py"] = req
        app = WebApp(state)
        files = app.get_files()
        assert len(files) == 1
        assert files[0]["file_path"] == "a.py"
        assert files[0]["decided"] is False

    def test_get_file_detail(self) -> None:
        state = MergeState(config=_make_config())
        req = _make_request("a.py")
        state.human_decision_requests["a.py"] = req
        app = WebApp(state)
        detail = app.get_file_detail("a.py")
        assert detail is not None
        assert detail["file_path"] == "a.py"
        assert len(detail["options"]) == 2

    def test_get_file_detail_not_found(self) -> None:
        state = MergeState(config=_make_config())
        app = WebApp(state)
        assert app.get_file_detail("nonexistent.py") is None

    def test_submit_decision_success(self) -> None:
        state = MergeState(config=_make_config())
        state.human_decision_requests["a.py"] = _make_request("a.py")
        app = WebApp(state)
        result = app.submit_decision("a.py", "take_target")
        assert result["success"] is True
        assert (
            state.human_decision_requests["a.py"].human_decision
            == MergeDecision.TAKE_TARGET
        )

    def test_submit_decision_invalid(self) -> None:
        state = MergeState(config=_make_config())
        state.human_decision_requests["a.py"] = _make_request("a.py")
        app = WebApp(state)
        result = app.submit_decision("a.py", "invalid_decision")
        assert result["success"] is False

    def test_submit_decision_not_found(self) -> None:
        state = MergeState(config=_make_config())
        app = WebApp(state)
        result = app.submit_decision("x.py", "take_target")
        assert result["success"] is False

    def test_submit_decision_escalate_blocked(self) -> None:
        state = MergeState(config=_make_config())
        state.human_decision_requests["a.py"] = _make_request("a.py")
        app = WebApp(state)
        result = app.submit_decision("a.py", "escalate_human")
        assert result["success"] is False

    def test_submit_manual_patch_no_content(self) -> None:
        state = MergeState(config=_make_config())
        state.human_decision_requests["a.py"] = _make_request("a.py")
        app = WebApp(state)
        result = app.submit_decision("a.py", "manual_patch")
        assert result["success"] is False

    def test_submit_manual_patch_with_content(self) -> None:
        state = MergeState(config=_make_config())
        state.human_decision_requests["a.py"] = _make_request("a.py")
        app = WebApp(state)
        result = app.submit_decision(
            "a.py", "manual_patch", custom_content="fixed code"
        )
        assert result["success"] is True

    def test_batch_decisions(self) -> None:
        state = MergeState(config=_make_config())
        state.human_decision_requests["a.py"] = _make_request("a.py")
        state.human_decision_requests["b.py"] = _make_request("b.py")
        app = WebApp(state)
        result = app.submit_batch_decisions(["a.py", "b.py"], "take_target")
        assert result["success"] is True
        assert result["succeeded"] == 2

    def test_all_decisions_complete(self) -> None:
        state = MergeState(config=_make_config())
        state.human_decision_requests["a.py"] = _make_request("a.py")
        app = WebApp(state)
        assert app.all_decisions_complete() is False
        app.submit_decision("a.py", "take_target")
        assert app.all_decisions_complete() is True

    def test_get_report(self) -> None:
        state = MergeState(config=_make_config())
        app = WebApp(state)
        report = app.get_report()
        assert "status" in report
