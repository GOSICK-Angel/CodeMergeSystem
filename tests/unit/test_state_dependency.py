"""Tests for MergeState.dependency_graph field."""

from src.models.config import MergeConfig
from src.models.dependency import (
    ConfidenceLabel,
    DependencyEdge,
    DependencyKind,
    FileDependencyGraph,
)
from src.models.state import MergeState


def _make_state() -> MergeState:
    config = MergeConfig(upstream_ref="upstream/main", fork_ref="feature/fork")
    return MergeState(config=config)


class TestStateDependencyGraph:
    def test_default_empty_graph(self):
        state = _make_state()
        assert isinstance(state.dependency_graph, FileDependencyGraph)
        assert len(state.dependency_graph.edges) == 0

    def test_assign_graph(self):
        state = _make_state()
        graph = FileDependencyGraph(
            edges=(
                DependencyEdge(
                    source_file="a.py",
                    target_file="b.py",
                    kind=DependencyKind.IMPORTS,
                ),
            ),
            file_count=2,
        )
        state.dependency_graph = graph
        assert len(state.dependency_graph.edges) == 1
        assert state.dependency_graph.file_count == 2

    def test_serialization_roundtrip(self):
        state = _make_state()
        state.dependency_graph = FileDependencyGraph(
            edges=(
                DependencyEdge(
                    source_file="x.py",
                    target_file="y.py",
                    kind=DependencyKind.INHERITS,
                    confidence=ConfidenceLabel.INFERRED,
                ),
            ),
            file_count=5,
        )
        data = state.model_dump(mode="json")
        assert "dependency_graph" in data

        restored = MergeState.model_validate(data)
        assert len(restored.dependency_graph.edges) == 1
        assert restored.dependency_graph.edges[0].kind == DependencyKind.INHERITS
        assert restored.dependency_graph.edges[0].confidence == ConfidenceLabel.INFERRED

    def test_backward_compat_no_field(self):
        state = _make_state()
        data = state.model_dump(mode="json")
        del data["dependency_graph"]
        restored = MergeState.model_validate(data)
        assert isinstance(restored.dependency_graph, FileDependencyGraph)
        assert len(restored.dependency_graph.edges) == 0
