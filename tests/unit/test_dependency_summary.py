"""Tests for dependency summary builder — generates text for agent prompts."""

from src.models.dependency import (
    DependencyEdge,
    DependencyKind,
    FileDependencyGraph,
)
from src.tools.dependency_extractor import (
    build_dependency_summary,
    build_impact_summary,
)


class TestBuildDependencySummary:
    def test_basic_summary(self):
        graph = FileDependencyGraph(
            edges=(
                DependencyEdge(
                    source_file="service.py",
                    target_file="base.py",
                    kind=DependencyKind.INHERITS,
                ),
                DependencyEdge(
                    source_file="handler.py",
                    target_file="base.py",
                    kind=DependencyKind.IMPORTS,
                ),
            )
        )
        result = build_dependency_summary(
            graph, ["base.py", "service.py", "handler.py"]
        )
        assert "base.py" in result
        assert "service.py" in result

    def test_suggested_order(self):
        graph = FileDependencyGraph(
            edges=(
                DependencyEdge(
                    source_file="c.py",
                    target_file="b.py",
                    kind=DependencyKind.IMPORTS,
                ),
                DependencyEdge(
                    source_file="b.py",
                    target_file="a.py",
                    kind=DependencyKind.IMPORTS,
                ),
            )
        )
        result = build_dependency_summary(graph, ["a.py", "b.py", "c.py"])
        order_line = [l for l in result.splitlines() if "Suggested merge order" in l]
        assert len(order_line) == 1
        assert order_line[0].index("a.py") < order_line[0].index("c.py")

    def test_empty_graph_returns_empty(self):
        graph = FileDependencyGraph()
        assert build_dependency_summary(graph, ["a.py", "b.py"]) == ""

    def test_no_relevant_edges(self):
        graph = FileDependencyGraph(
            edges=(
                DependencyEdge(
                    source_file="x.py",
                    target_file="y.py",
                    kind=DependencyKind.IMPORTS,
                ),
            )
        )
        assert build_dependency_summary(graph, ["a.py", "b.py"]) == ""

    def test_empty_file_list(self):
        graph = FileDependencyGraph()
        assert build_dependency_summary(graph, []) == ""


class TestBuildImpactSummary:
    def test_impact_summary(self):
        graph = FileDependencyGraph(
            edges=(
                DependencyEdge(
                    source_file="b.py",
                    target_file="a.py",
                    kind=DependencyKind.IMPORTS,
                ),
                DependencyEdge(
                    source_file="c.py",
                    target_file="a.py",
                    kind=DependencyKind.IMPORTS,
                ),
            )
        )
        result = build_impact_summary(graph, "a.py")
        assert "b.py" in result
        assert "c.py" in result

    def test_no_impact(self):
        graph = FileDependencyGraph()
        assert build_impact_summary(graph, "a.py") == ""
