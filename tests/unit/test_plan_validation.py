"""Hard-validation of MergePlan layer dependency graph.

Regression: run 19ac33d6 had a plan whose layer 3 declared depends_on=[2]
while layer 2 was absent from plan.layers. `verify_layer_deps` then
silently skipped 223 files (drift threshold tripped, $14.86 wasted on
judge calls). validate_plan_shape must catch this before LLM judge runs.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.models.diff import RiskLevel
from src.models.plan import (
    MergeLayer,
    MergePhase,
    MergePlan,
    PhaseFileBatch,
    PlanValidationError,
    RiskSummary,
    validate_plan_shape,
)


def _risk_summary() -> RiskSummary:
    return RiskSummary(
        total_files=0,
        auto_safe_count=0,
        auto_risky_count=0,
        human_required_count=0,
        deleted_only_count=0,
        binary_count=0,
        excluded_count=0,
        estimated_auto_merge_rate=0.0,
    )


def _make_plan(
    layers: list[MergeLayer], phases: list[PhaseFileBatch]
) -> MergePlan:
    return MergePlan(
        created_at=datetime.now(),
        upstream_ref="upstream/main",
        fork_ref="feat_merge",
        merge_base_commit="abc123",
        phases=phases,
        risk_summary=_risk_summary(),
        layers=layers,
        project_context_summary="test",
    )


def test_healthy_plan_passes() -> None:
    plan = _make_plan(
        layers=[
            MergeLayer(layer_id=0, name="base"),
            MergeLayer(layer_id=1, name="services", depends_on=[0]),
            MergeLayer(layer_id=2, name="api", depends_on=[1]),
        ],
        phases=[
            PhaseFileBatch(
                batch_id="b0",
                phase=MergePhase.AUTO_MERGE,
                file_paths=["a.py"],
                risk_level=RiskLevel.AUTO_SAFE,
                layer_id=0,
            ),
            PhaseFileBatch(
                batch_id="b2",
                phase=MergePhase.AUTO_MERGE,
                file_paths=["c.py"],
                risk_level=RiskLevel.AUTO_SAFE,
                layer_id=2,
            ),
        ],
    )
    validate_plan_shape(plan)


def test_phantom_dep_raises_with_specific_layer_ids() -> None:
    """Reproduces the run-19ac33d6 bug: layer references undeclared layer."""
    plan = _make_plan(
        layers=[
            MergeLayer(layer_id=0, name="base"),
            MergeLayer(layer_id=3, name="aihubmix", depends_on=[2]),
        ],
        phases=[],
    )
    with pytest.raises(PlanValidationError) as exc_info:
        validate_plan_shape(plan)
    msg = str(exc_info.value)
    assert "layer 3" in msg
    assert "[2]" in msg
    assert "not declared" in msg


def test_cycle_raises() -> None:
    plan = _make_plan(
        layers=[
            MergeLayer(layer_id=0, name="a", depends_on=[1]),
            MergeLayer(layer_id=1, name="b", depends_on=[0]),
        ],
        phases=[],
    )
    with pytest.raises(PlanValidationError) as exc_info:
        validate_plan_shape(plan)
    assert "Cycle" in str(exc_info.value)


def test_phase_batch_phantom_layer_raises() -> None:
    """A batch with layer_id=99 but plan.layers has no layer 99 must fail
    — auto_merge would silently skip it under verify_layer_deps."""
    plan = _make_plan(
        layers=[MergeLayer(layer_id=0, name="base")],
        phases=[
            PhaseFileBatch(
                batch_id="orphan_batch",
                phase=MergePhase.AUTO_MERGE,
                file_paths=["x.py"],
                risk_level=RiskLevel.AUTO_SAFE,
                layer_id=99,
            )
        ],
    )
    with pytest.raises(PlanValidationError) as exc_info:
        validate_plan_shape(plan)
    msg = str(exc_info.value)
    assert "orphan_batch" in msg
    assert "99" in msg


def test_no_layers_passes() -> None:
    """Plan with no layer graph (older plans / trivial cases) is allowed."""
    plan = _make_plan(
        layers=[],
        phases=[
            PhaseFileBatch(
                batch_id="b1",
                phase=MergePhase.AUTO_MERGE,
                file_paths=["a.py"],
                risk_level=RiskLevel.AUTO_SAFE,
            )
        ],
    )
    validate_plan_shape(plan)


def test_none_plan_passes() -> None:
    """Caller may pass None during early init; validator must not crash."""
    validate_plan_shape(None)  # type: ignore[arg-type]


def test_phantom_dep_aggregates_all_problems() -> None:
    """Multiple defects should all surface in one error message."""
    plan = _make_plan(
        layers=[
            MergeLayer(layer_id=0, name="a"),
            MergeLayer(layer_id=3, name="b", depends_on=[2]),
            MergeLayer(layer_id=4, name="c", depends_on=[5]),
        ],
        phases=[],
    )
    with pytest.raises(PlanValidationError) as exc_info:
        validate_plan_shape(plan)
    msg = str(exc_info.value)
    assert "layer 3" in msg and "[2]" in msg
    assert "layer 4" in msg and "[5]" in msg
