"""Detect unresolved git merge conflict markers in file content.

O-M1: cherry-pick fall-back can leave ``<<<<<<<`` / ``=======`` / ``>>>>>>>``
markers in the working tree. Send those straight to human review instead of
feeding them into the AUTO_MERGE / Judge pipeline.
"""

from __future__ import annotations

from pathlib import Path

CONFLICT_MARKERS: tuple[str, ...] = ("<<<<<<<", "=======", ">>>>>>>")


def has_conflict_markers(content: str) -> bool:
    if not content:
        return False
    return any(marker in content for marker in CONFLICT_MARKERS)


def safe_read_text(abs_path: Path) -> str | None:
    try:
        return abs_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, PermissionError, IsADirectoryError):
        return None


def file_has_conflict_markers(repo_path: Path, file_path: str) -> bool:
    abs_path = repo_path / file_path
    if not abs_path.is_file():
        return False
    content = safe_read_text(abs_path)
    if content is None:
        return False
    return has_conflict_markers(content)
