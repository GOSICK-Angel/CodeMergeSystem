import pytest
from src.tools.conflict_grouper import group_similar_conflicts, ConflictGroup
from src.models.conflict import ConflictAnalysis, ConflictType
from src.models.decision import MergeDecision


def _make_analysis(
    file_path: str,
    conflict_type: ConflictType = ConflictType.DEPENDENCY_UPDATE,
    strategy: MergeDecision = MergeDecision.TAKE_TARGET,
    confidence: float = 0.8,
) -> ConflictAnalysis:
    return ConflictAnalysis(
        file_path=file_path,
        conflict_points=[],
        overall_confidence=confidence,
        recommended_strategy=strategy,
        conflict_type=conflict_type,
        confidence=confidence,
    )


class TestGroupSimilarConflicts:
    def test_empty_input(self) -> None:
        result = group_similar_conflicts({})
        assert result == []

    def test_single_file_no_group(self) -> None:
        analyses = {"a.py": _make_analysis("a.py")}
        result = group_similar_conflicts(analyses)
        assert result == []

    def test_two_same_type_grouped(self) -> None:
        analyses = {
            "a.py": _make_analysis(
                "a.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
            "b.py": _make_analysis(
                "b.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
        }
        result = group_similar_conflicts(analyses)
        assert len(result) == 1
        assert len(result[0].file_paths) == 2

    def test_different_types_not_grouped(self) -> None:
        analyses = {
            "a.py": _make_analysis("a.py", ConflictType.DEPENDENCY_UPDATE),
            "b.py": _make_analysis("b.py", ConflictType.LOGIC_CONTRADICTION),
        }
        result = group_similar_conflicts(analyses)
        assert result == []

    def test_same_type_different_strategy_not_grouped(self) -> None:
        analyses = {
            "a.py": _make_analysis(
                "a.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
            "b.py": _make_analysis(
                "b.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_CURRENT
            ),
        }
        result = group_similar_conflicts(analyses)
        assert result == []

    def test_multiple_groups(self) -> None:
        analyses = {
            "a.py": _make_analysis(
                "a.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
            "b.py": _make_analysis(
                "b.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
            "c.py": _make_analysis(
                "c.py", ConflictType.CONFIGURATION, MergeDecision.SEMANTIC_MERGE
            ),
            "d.py": _make_analysis(
                "d.py", ConflictType.CONFIGURATION, MergeDecision.SEMANTIC_MERGE
            ),
        }
        result = group_similar_conflicts(analyses)
        assert len(result) == 2

    def test_groups_sorted_by_size(self) -> None:
        analyses = {
            "a.py": _make_analysis(
                "a.py", ConflictType.CONFIGURATION, MergeDecision.TAKE_TARGET
            ),
            "b.py": _make_analysis(
                "b.py", ConflictType.CONFIGURATION, MergeDecision.TAKE_TARGET
            ),
            "c.py": _make_analysis(
                "c.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
            "d.py": _make_analysis(
                "d.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
            "e.py": _make_analysis(
                "e.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
        }
        result = group_similar_conflicts(analyses)
        assert len(result) == 2
        assert len(result[0].file_paths) >= len(result[1].file_paths)

    def test_representative_file_is_first_sorted(self) -> None:
        analyses = {
            "z.py": _make_analysis(
                "z.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
            "a.py": _make_analysis(
                "a.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
        }
        result = group_similar_conflicts(analyses)
        assert result[0].representative_file == "a.py"

    def test_group_has_correct_fields(self) -> None:
        analyses = {
            "x.py": _make_analysis(
                "x.py", ConflictType.CONFIGURATION, MergeDecision.TAKE_TARGET
            ),
            "y.py": _make_analysis(
                "y.py", ConflictType.CONFIGURATION, MergeDecision.TAKE_TARGET
            ),
        }
        result = group_similar_conflicts(analyses)
        assert len(result) == 1
        group = result[0]
        assert group.conflict_type == ConflictType.CONFIGURATION
        assert "configuration" in group.pattern_description
        assert "take_target" in group.pattern_description
        assert group.file_paths == ["x.py", "y.py"]
        assert group.group_id

    def test_file_paths_are_sorted(self) -> None:
        analyses = {
            "c.py": _make_analysis(
                "c.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
            "a.py": _make_analysis(
                "a.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
            "b.py": _make_analysis(
                "b.py", ConflictType.DEPENDENCY_UPDATE, MergeDecision.TAKE_TARGET
            ),
        }
        result = group_similar_conflicts(analyses)
        assert result[0].file_paths == ["a.py", "b.py", "c.py"]
