"""Tests for RuleBasedResolver — deterministic conflict pre-resolution."""

from __future__ import annotations

from src.tools.rule_resolver import RuleBasedResolver, RulePattern, RuleResolution


class TestIdenticalChange:
    def test_identical_content(self):
        resolver = RuleBasedResolver()
        result = resolver.try_resolve("base", "same", "same")
        assert result.resolved is True
        assert result.pattern == RulePattern.IDENTICAL_CHANGE
        assert result.confidence == 1.0
        assert result.merged_content == "same"

    def test_different_content_not_identical(self):
        resolver = RuleBasedResolver()
        result = resolver.try_resolve("base", "current", "target")
        assert result.pattern != RulePattern.IDENTICAL_CHANGE or not result.resolved


class TestWhitespaceOnly:
    def test_trailing_whitespace_diff(self):
        resolver = RuleBasedResolver()
        base = "line1\nline2"
        current = "line1  \nline2  "
        target = "line1\nline2"
        result = resolver.try_resolve(base, current, target)
        assert result.resolved is True
        assert result.pattern == RulePattern.WHITESPACE_ONLY

    def test_current_whitespace_only_change(self):
        resolver = RuleBasedResolver()
        base = "a\nb\nc"
        current = "a  \nb  \nc  "
        target = "a\nB\nc"
        result = resolver.try_resolve(base, current, target)
        assert result.resolved is True
        assert result.pattern == RulePattern.WHITESPACE_ONLY
        assert result.merged_content == target

    def test_target_whitespace_only_change(self):
        resolver = RuleBasedResolver()
        base = "a\nb\nc"
        current = "a\nB\nc"
        target = "a  \nb  \nc  "
        result = resolver.try_resolve(base, current, target)
        assert result.resolved is True
        assert result.pattern == RulePattern.WHITESPACE_ONLY
        assert result.merged_content == current

    def test_real_changes_not_whitespace(self):
        resolver = RuleBasedResolver()
        result = resolver.try_resolve("a\nb", "a\nX", "a\nY")
        assert result.pattern != RulePattern.WHITESPACE_ONLY or not result.resolved


class TestImportUnion:
    def test_both_add_different_imports(self):
        resolver = RuleBasedResolver()
        base = "import os\n\nx = 1"
        current = "import os\nimport sys\n\nx = 1"
        target = "import os\nimport json\n\nx = 1"
        result = resolver.try_resolve(base, current, target)
        assert result.resolved is True
        assert result.pattern == RulePattern.IMPORT_UNION
        assert "import sys" in result.merged_content
        assert "import json" in result.merged_content
        assert "import os" in result.merged_content

    def test_no_imports(self):
        resolver = RuleBasedResolver()
        base = "x = 1\ny = 2"
        current = "x = 1\ny = 3"
        target = "x = 1\ny = 4"
        result = resolver.try_resolve(base, current, target)
        assert result.pattern != RulePattern.IMPORT_UNION or not result.resolved

    def test_conflicting_import_removal(self):
        resolver = RuleBasedResolver()
        base = "import os\nimport sys\n\nx = 1"
        current = "import os\n\nx = 1"
        target = "import os\nimport sys\nimport json\n\nx = 1"
        result = resolver.try_resolve(base, current, target)
        assert not result.resolved or result.pattern != RulePattern.IMPORT_UNION


class TestAdjacentEdit:
    def test_non_overlapping_edits(self):
        resolver = RuleBasedResolver()
        base = "a\nb\nc\nd\ne"
        current = "A\nb\nc\nd\ne"
        target = "a\nb\nc\nd\nE"
        result = resolver.try_resolve(base, current, target)
        assert result.resolved is True
        assert result.pattern == RulePattern.ADJACENT_EDIT
        assert result.merged_content == "A\nb\nc\nd\nE"

    def test_overlapping_edits_not_resolved(self):
        resolver = RuleBasedResolver()
        base = "a\nb\nc"
        current = "X\nb\nc"
        target = "Y\nb\nc"
        result = resolver.try_resolve(base, current, target)
        assert result.pattern != RulePattern.ADJACENT_EDIT or not result.resolved

    def test_different_line_count_not_adjacent(self):
        resolver = RuleBasedResolver()
        base = "a\nb\nc"
        current = "a\nb\nc\nd"
        target = "a\nb\nC"
        result = resolver.try_resolve(base, current, target)
        assert result.pattern != RulePattern.ADJACENT_EDIT or not result.resolved


class TestNoneInputs:
    def test_none_base(self):
        resolver = RuleBasedResolver()
        result = resolver.try_resolve(None, "a", "b")
        assert result.resolved is False

    def test_none_current(self):
        resolver = RuleBasedResolver()
        result = resolver.try_resolve("a", None, "b")
        assert result.resolved is False

    def test_none_target(self):
        resolver = RuleBasedResolver()
        result = resolver.try_resolve("a", "b", None)
        assert result.resolved is False

    def test_all_none(self):
        resolver = RuleBasedResolver()
        result = resolver.try_resolve(None, None, None)
        assert result.resolved is False


class TestResolutionModel:
    def test_default_values(self):
        r = RuleResolution()
        assert r.resolved is False
        assert r.pattern is None
        assert r.merged_content == ""
        assert r.confidence == 0.0

    def test_serialization(self):
        r = RuleResolution(
            resolved=True,
            pattern=RulePattern.ADJACENT_EDIT,
            merged_content="merged",
            confidence=0.85,
            description="test",
        )
        data = r.model_dump()
        restored = RuleResolution.model_validate(data)
        assert restored.resolved is True
        assert restored.pattern == RulePattern.ADJACENT_EDIT


class TestPriorityOrder:
    def test_identical_takes_priority_over_whitespace(self):
        resolver = RuleBasedResolver()
        result = resolver.try_resolve("base", "same", "same")
        assert result.pattern == RulePattern.IDENTICAL_CHANGE

    def test_whitespace_checked_before_import(self):
        resolver = RuleBasedResolver()
        base = "import os\n\nx = 1"
        current = "import os  \n\nx = 1  "
        target = "import os\n\nx = 1"
        result = resolver.try_resolve(base, current, target)
        assert result.resolved is True
        assert result.pattern == RulePattern.WHITESPACE_ONLY
