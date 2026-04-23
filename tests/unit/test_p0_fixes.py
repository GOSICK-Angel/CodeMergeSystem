"""Unit tests for P0 fixes from the upstream-50-commits-v2 test report:

- O-M1: conflict-marker detection + escalation paths
- O-M2: judge_blocking_levels controls BatchVerdict.approved
- O-L3: auto_merge no-consensus creates HumanDecisionRequests and marks the
  layer exhausted so HumanReviewPhase does not loop back to AUTO_MERGING.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agents.judge_agent import JudgeAgent
from src.core.phases.human_review import HumanReviewPhase
from src.core.read_only_state_view import ReadOnlyStateView
from src.models.config import AgentLLMConfig, MergeConfig
from src.models.decision import FileDecisionRecord, MergeDecision
from src.models.diff import FileStatus
from src.models.judge import BatchVerdict, IssueSeverity, JudgeIssue
from src.models.plan_review import (
    PlanHumanDecision,
    PlanHumanReview,
)
from src.models.state import MergeState, SystemStatus
from src.tools.conflict_markers import (
    file_has_conflict_markers,
    has_conflict_markers,
)
from src.tools.patch_applier import apply_with_snapshot


# --------------------------------------------------------------------------
# O-M1: conflict-marker detection
# --------------------------------------------------------------------------


def test_has_conflict_markers_detects_all_three():
    assert has_conflict_markers("a\n<<<<<<< HEAD\nb\n=======\nc\n>>>>>>> up\n")
    assert has_conflict_markers("<<<<<<< only\n")
    assert has_conflict_markers("line\n=======\nline")
    assert has_conflict_markers(">>>>>>> trail\n")


def test_has_conflict_markers_clean_content():
    assert not has_conflict_markers("")
    assert not has_conflict_markers("def foo():\n    return 1\n")
    # Shorter-than-7 angle brackets should not trip it.
    assert not has_conflict_markers("<<<<<<\n======\n>>>>>>\n")


def test_file_has_conflict_markers_reads_from_repo():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        p = repo / "a" / "b.yaml"
        p.parent.mkdir(parents=True)
        p.write_text("ok\n", encoding="utf-8")
        assert not file_has_conflict_markers(repo, "a/b.yaml")

        p.write_text("x\n<<<<<<< HEAD\n=======\n>>>>>>> up\n", encoding="utf-8")
        assert file_has_conflict_markers(repo, "a/b.yaml")


def test_file_has_conflict_markers_handles_binary_gracefully():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        p = repo / "icon.png"
        # PNG magic bytes — not valid UTF-8.
        p.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
        # Must not raise; returns False.
        assert file_has_conflict_markers(repo, "icon.png") is False


def test_file_has_conflict_markers_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        assert file_has_conflict_markers(repo, "does/not/exist.py") is False


@pytest.mark.asyncio
async def test_apply_with_snapshot_rejects_conflict_markers():
    """O-M1: patch_applier refuses to write content containing markers."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        target = repo / "file.py"
        target.write_text("original\n", encoding="utf-8")

        git_tool = MagicMock()
        git_tool.repo_path = repo

        state = MergeState(config=MergeConfig(upstream_ref="upstream", fork_ref="fork"))

        bad = "line\n<<<<<<< HEAD\nold\n=======\nnew\n>>>>>>> up\n"
        record = await apply_with_snapshot(
            file_path="file.py",
            new_content=bad,
            git_tool=git_tool,
            state=state,
        )

        assert record.decision == MergeDecision.ESCALATE_HUMAN
        assert record.confidence == 0.0
        assert record.rollback_reason == "conflict_markers_in_proposed_content"
        # Original file must NOT have been overwritten.
        assert target.read_text(encoding="utf-8") == "original\n"


# --------------------------------------------------------------------------
# O-M2: judge_blocking_levels controls approval
# --------------------------------------------------------------------------


def _make_readonly_view(blocking_levels: list[str] | None = None) -> ReadOnlyStateView:
    kwargs: dict[str, object] = {
        "upstream_ref": "upstream",
        "fork_ref": "fork",
    }
    if blocking_levels is not None:
        kwargs["judge_blocking_levels"] = blocking_levels
    cfg = MergeConfig(**kwargs)
    state = MergeState(config=cfg)
    return ReadOnlyStateView(state)


def _make_judge() -> JudgeAgent:
    llm_config = AgentLLMConfig(
        provider="anthropic",
        model="claude-opus-4-6",
        api_key_env="ANTHROPIC_API_KEY",
    )
    return JudgeAgent(llm_config=llm_config)


def _issue(level: IssueSeverity, must_fix: bool = False) -> JudgeIssue:
    return JudgeIssue(
        file_path="f.py",
        issue_level=level,
        issue_type="other",
        description="x",
        must_fix_before_merge=must_fix,
    )


def test_compute_approved_info_only_is_approved():
    """Default blocking levels = {critical, high}; info/low advisory issues
    alone must not block approval."""
    judge = _make_judge()
    view = _make_readonly_view()
    assert (
        judge._compute_batch_approved(
            [_issue(IssueSeverity.INFO), _issue(IssueSeverity.LOW)],
            view,
        )
        is True
    )


def test_compute_approved_critical_blocks():
    judge = _make_judge()
    view = _make_readonly_view()
    assert (
        judge._compute_batch_approved([_issue(IssueSeverity.CRITICAL)], view) is False
    )


def test_compute_approved_high_blocks_by_default():
    judge = _make_judge()
    view = _make_readonly_view()
    assert judge._compute_batch_approved([_issue(IssueSeverity.HIGH)], view) is False


def test_compute_approved_must_fix_blocks_regardless_of_level():
    """Even an ``info`` issue with ``must_fix_before_merge=True`` still blocks
    (this is the path used by the deterministic ``=======`` marker check)."""
    judge = _make_judge()
    view = _make_readonly_view()
    assert (
        judge._compute_batch_approved([_issue(IssueSeverity.INFO, must_fix=True)], view)
        is False
    )


def test_compute_approved_custom_blocking_levels_medium():
    judge = _make_judge()
    view = _make_readonly_view(blocking_levels=["critical", "high", "medium"])
    assert judge._compute_batch_approved([_issue(IssueSeverity.MEDIUM)], view) is False
    assert judge._compute_batch_approved([_issue(IssueSeverity.LOW)], view) is True


def test_compute_approved_llm_opinion_ignored_without_blocking_levels():
    """When LLM says not-approved but only info/low issues remain, we still
    approve (advisories do not block)."""
    judge = _make_judge()
    view = _make_readonly_view()
    assert (
        judge._compute_batch_approved(
            [_issue(IssueSeverity.INFO)], view, llm_opinion=False
        )
        is True
    )


def test_compute_approved_llm_opinion_honored_with_blocking_levels():
    judge = _make_judge()
    view = _make_readonly_view()
    # critical issue present — regardless of LLM opinion, we block.
    assert (
        judge._compute_batch_approved(
            [_issue(IssueSeverity.CRITICAL)], view, llm_opinion=True
        )
        is False
    )


# --------------------------------------------------------------------------
# O-L3: dispute-exhaustion creates HumanDecisionRequests and the
# HumanReviewPhase routes to JUDGE_REVIEWING, not back to AUTO_MERGING.
# --------------------------------------------------------------------------


def _make_state_with_approved_plan() -> MergeState:
    cfg = MergeConfig(upstream_ref="upstream", fork_ref="fork")
    state = MergeState(config=cfg)
    state.plan_human_review = PlanHumanReview(
        decision=PlanHumanDecision.APPROVE,
        reviewer_name="tester",
    )
    return state


def test_register_dispute_exhaustion_creates_requests_and_tag():
    from src.core.phases.auto_merge import AutoMergePhase

    phase = AutoMergePhase()
    state = _make_state_with_approved_plan()
    issues = [
        JudgeIssue(
            file_path="a.py",
            issue_level=IssueSeverity.CRITICAL,
            issue_type="unresolved_conflict",
            description="Conflict marker '=======' found",
            must_fix_before_merge=True,
        ),
        JudgeIssue(
            file_path="b.py",
            issue_level=IssueSeverity.HIGH,
            issue_type="missing_logic",
            description="Fork logic dropped",
        ),
    ]
    verdict = BatchVerdict(layer_id=2, approved=False, issues=issues)

    phase._register_dispute_exhaustion(
        state=state,
        layer_id=2,
        layer_files=["a.py", "b.py", "c.py"],
        batch_verdict=verdict,
        max_dispute=2,
    )

    assert state.auto_merge_dispute_exhausted_layers == ["2"]
    assert set(state.human_decision_requests.keys()) == {"a.py", "b.py", "c.py"}
    for req in state.human_decision_requests.values():
        assert req.analyst_recommendation == MergeDecision.ESCALATE_HUMAN
        option_keys = {opt.option_key for opt in req.options}
        assert option_keys == {"approve_merge", "take_target", "take_current"}

    a_req = state.human_decision_requests["a.py"]
    # Preview includes at least the issue description.
    assert "Conflict marker" in (a_req.options[0].preview_content or "")


def test_register_dispute_exhaustion_preserves_existing_request():
    from src.core.phases.auto_merge import AutoMergePhase
    from src.models.human import (
        DecisionOption as HumanDecisionOption,
    )
    from src.models.human import HumanDecisionRequest
    from datetime import datetime

    phase = AutoMergePhase()
    state = _make_state_with_approved_plan()
    # Pre-seed an existing request for 'a.py' — should not be overwritten.
    state.human_decision_requests["a.py"] = HumanDecisionRequest(
        file_path="a.py",
        priority=7,
        conflict_points=[],
        context_summary="pre-existing",
        upstream_change_summary="x",
        fork_change_summary="y",
        analyst_recommendation=MergeDecision.TAKE_TARGET,
        analyst_confidence=0.8,
        analyst_rationale="existing rationale",
        options=[
            HumanDecisionOption(
                option_key="keep",
                decision=MergeDecision.TAKE_CURRENT,
                description="keep",
            )
        ],
        created_at=datetime.now(),
    )
    verdict = BatchVerdict(layer_id=None, approved=False, issues=[])

    phase._register_dispute_exhaustion(
        state=state,
        layer_id=None,
        layer_files=["a.py", "b.py"],
        batch_verdict=verdict,
        max_dispute=2,
    )

    assert state.auto_merge_dispute_exhausted_layers == ["None"]
    # 'a.py' preserved — context_summary must still read "pre-existing"
    assert state.human_decision_requests["a.py"].context_summary == "pre-existing"
    # 'b.py' newly created
    assert "b.py" in state.human_decision_requests


@pytest.mark.asyncio
async def test_human_review_reroutes_when_auto_merge_exhausted():
    """O-L3 guard: when ``auto_merge_dispute_exhausted_layers`` is populated
    and the plan is approved, HumanReviewPhase must route to JUDGE_REVIEWING
    instead of looping back to AUTO_MERGING."""
    state = _make_state_with_approved_plan()
    state.auto_merge_dispute_exhausted_layers = ["None"]

    ctx = MagicMock()
    ctx.config.output.directory = "./outputs"
    ctx.state_machine.transition = MagicMock()

    # Bypass report-writing side effect.
    import src.core.phases.human_review as hr_mod

    original_writer = hr_mod.write_plan_review_report
    hr_mod.write_plan_review_report = MagicMock(return_value=None)
    try:
        outcome = await HumanReviewPhase().execute(state, ctx)
    finally:
        hr_mod.write_plan_review_report = original_writer

    assert outcome.target_status == SystemStatus.JUDGE_REVIEWING
    # Assert the transition was called with JUDGE_REVIEWING, not AUTO_MERGING.
    call_args = ctx.state_machine.transition.call_args
    assert call_args.args[1] == SystemStatus.JUDGE_REVIEWING


@pytest.mark.asyncio
async def test_human_review_normal_plan_approve_still_goes_to_auto_merging():
    """Regression guard: without dispute exhaustion, plan-approve still
    transitions to AUTO_MERGING as before."""
    state = _make_state_with_approved_plan()
    # No exhausted layers.
    assert state.auto_merge_dispute_exhausted_layers == []

    ctx = MagicMock()
    ctx.config.output.directory = "./outputs"
    ctx.state_machine.transition = MagicMock()

    import src.core.phases.human_review as hr_mod

    original_writer = hr_mod.write_plan_review_report
    hr_mod.write_plan_review_report = MagicMock(return_value=None)
    try:
        outcome = await HumanReviewPhase().execute(state, ctx)
    finally:
        hr_mod.write_plan_review_report = original_writer

    assert outcome.target_status == SystemStatus.AUTO_MERGING


# --------------------------------------------------------------------------
# Regression: existing FileDecisionRecord shape still accepts escalate
# records produced by patch_applier's O-M1 path.
# --------------------------------------------------------------------------


def test_escalate_record_from_conflict_markers_is_well_formed():
    from src.models.decision import DecisionSource

    rec = FileDecisionRecord(
        file_path="x.py",
        file_status=FileStatus.MODIFIED,
        decision=MergeDecision.ESCALATE_HUMAN,
        decision_source=DecisionSource.AUTO_EXECUTOR,
        rationale="Unresolved conflict markers detected (O-M1)",
        confidence=0.0,
    )
    assert rec.decision == MergeDecision.ESCALATE_HUMAN
    assert rec.confidence == 0.0
