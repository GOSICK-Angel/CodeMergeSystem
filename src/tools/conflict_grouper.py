from uuid import uuid4

from pydantic import BaseModel, Field

from src.models.conflict import ConflictAnalysis, ConflictType


class ConflictGroup(BaseModel):
    group_id: str = Field(default_factory=lambda: str(uuid4()))
    conflict_type: ConflictType
    pattern_description: str
    file_paths: list[str]
    representative_file: str


def group_similar_conflicts(
    analyses: dict[str, ConflictAnalysis],
) -> list[ConflictGroup]:
    """Group similar conflicts for batch decision-making.

    Groups by same conflict_type AND same recommended_strategy.
    Only creates groups with 2+ files.
    """
    if not analyses:
        return []

    buckets: dict[tuple[str, str], list[str]] = {}
    for file_path, analysis in analyses.items():
        ct = (
            analysis.conflict_type.value
            if hasattr(analysis.conflict_type, "value")
            else str(analysis.conflict_type)
        )
        rs = (
            analysis.recommended_strategy.value
            if hasattr(analysis.recommended_strategy, "value")
            else str(analysis.recommended_strategy)
        )
        key = (ct, rs)
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(file_path)

    groups: list[ConflictGroup] = []
    for (ct_val, rs_val), paths in buckets.items():
        if len(paths) < 2:
            continue
        try:
            ct = ConflictType(ct_val)
        except ValueError:
            ct = ConflictType.UNKNOWN
        sorted_paths = sorted(paths)
        groups.append(
            ConflictGroup(
                group_id=str(uuid4()),
                conflict_type=ct,
                pattern_description=(
                    f"{ct_val} conflicts with recommended strategy: {rs_val}"
                ),
                file_paths=sorted_paths,
                representative_file=sorted_paths[0],
            )
        )

    return sorted(groups, key=lambda g: len(g.file_paths), reverse=True)
