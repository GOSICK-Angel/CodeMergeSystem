"""Integration regression tests for P0 hardening.

Each test reconstructs a minimal scenario mirroring a real past bug
(from §10 appendix of multi-agent-optimization doc) and verifies the new
gate would have caught it. No real LLM / external API calls.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents.judge_agent import JudgeAgent
from src.agents.planner_agent import PlannerAgent
from src.core.read_only_state_view import ReadOnlyStateView
from src.models.config import (
    AgentLLMConfig,
    CrossLayerAssertion,
    CustomizationEntry,
    CustomizationVerification,
    MergeConfig,
)
from src.models.diff import FileChangeCategory, FileDiff, FileStatus, RiskLevel
from src.models.state import MergeState
from src.tools.shadow_conflict_detector import ShadowConflictDetector


class _RegressionGit:
    """Minimal git stub: serves file content per ref + repo_path for HEAD reads."""

    def __init__(self, repo_path: Path, refs: dict[str, dict[str, str]]):
        self.repo_path = repo_path
        self._refs = refs

    def get_file_content(self, ref: str, file_path: str) -> str | None:
        return self._refs.get(ref, {}).get(file_path)

    def list_files(self, ref: str) -> list[str]:
        return list(self._refs.get(ref, {}).keys())

    def grep_in_files(
        self, pattern: str, file_patterns: list[str]
    ) -> dict[str, list[str]]:
        import fnmatch
        import re

        compiled = re.compile(pattern)
        results: dict[str, list[str]] = {}
        all_files = [
            str(p.relative_to(self.repo_path))
            for p in self.repo_path.rglob("*")
            if p.is_file()
        ]
        for fp in all_files:
            if not any(fnmatch.fnmatch(fp, gp) for gp in file_patterns):
                continue
            try:
                content = (self.repo_path / fp).read_text(encoding="utf-8")
            except Exception:
                continue
            matches = compiled.findall(content)
            if matches:
                results[fp] = matches
        return results


def _judge(git):
    with patch("src.llm.client.LLMClientFactory.create"):
        return JudgeAgent(AgentLLMConfig(), git_tool=git)


# ─── Regression M4: 顶层 api.add_resource 整体丢失 ────────────────────────────


def test_regression_m4_top_level_invocations_lost(tmp_path):
    (tmp_path / "workspace.py").write_text(
        "class WorkspaceListApi:\n    pass\n"
        "# upstream merged but every api.add_resource line dropped\n"
    )
    base = (
        "class WorkspaceListApi:\n    pass\n"
        "api.add_resource(WorkspaceListApi, '/workspaces')\n"
        "api.add_resource(WorkspaceApi, '/workspace/<id>')\n"
    )
    upstream = (
        "class WorkspaceListApi:\n    pass\n"
        "api.add_resource(WorkspaceListApi, '/workspaces')\n"
        "api.add_resource(WorkspaceApi, '/workspace/<id>')\n"
        "api.add_resource(WorkspaceMemberApi, '/workspace/<id>/members')\n"
    )
    git = _RegressionGit(
        tmp_path,
        {
            "base-sha": {"workspace.py": base},
            "upstream/main": {"workspace.py": upstream},
        },
    )
    judge = _judge(git)

    config = MergeConfig(
        upstream_ref="upstream/main",
        fork_ref="feature/fork",
        repo_path=str(tmp_path),
    )
    state = MergeState(config=config)
    state.merge_base_commit = "base-sha"
    state.file_categories = {"workspace.py": FileChangeCategory.C}

    view = ReadOnlyStateView(state)
    issues = judge._check_top_level_invocations(
        view, {"workspace.py": FileChangeCategory.C}
    )
    assert any(i.issue_type == "top_level_invocation_lost" for i in issues)


# ─── Regression M2: context.ts vs context.tsx shadow pair ─────────────────────


def test_regression_m2_shadow_conflict_promotes_to_human(tmp_path):
    detector = ShadowConflictDetector()
    conflicts = detector.detect(["web/app/chat/context.ts", "web/app/chat/context.tsx"])
    assert len(conflicts) == 1

    with patch("src.llm.client.LLMClientFactory.create"):
        planner = PlannerAgent(AgentLLMConfig())

    config = MergeConfig(upstream_ref="upstream/main", fork_ref="feature/fork")
    state = MergeState(config=config)
    state.merge_base_commit = "base-sha"
    state.file_categories = {
        "web/app/chat/context.ts": FileChangeCategory.C,
        "web/app/chat/context.tsx": FileChangeCategory.D_MISSING,
    }
    fd_ts = FileDiff(
        file_path="web/app/chat/context.ts",
        file_status=FileStatus.MODIFIED,
        risk_level=RiskLevel.AUTO_SAFE,
        risk_score=0.1,
        change_category=FileChangeCategory.C,
    )
    fd_tsx = FileDiff(
        file_path="web/app/chat/context.tsx",
        file_status=FileStatus.ADDED,
        risk_level=RiskLevel.AUTO_SAFE,
        risk_score=0.1,
        change_category=FileChangeCategory.D_MISSING,
    )
    state.file_diffs = [fd_ts, fd_tsx]

    plan = planner._build_layered_plan(state.file_diffs, state)
    human = {
        fp
        for phase in plan.phases
        if phase.risk_level == RiskLevel.HUMAN_REQUIRED
        for fp in phase.file_paths
    }
    assert "web/app/chat/context.tsx" in human
    assert len(state.shadow_conflicts) == 1


# ─── Regression M1: grep count baseline drop ──────────────────────────────────


def test_regression_m1_grep_count_baseline_drop(tmp_path):
    (tmp_path / "engine.py").write_text("skill_id = 'abc'\n")
    baseline_content = (
        "skill_id = 'a'\n"
        "skill_id = 'b'\n"
        "skill_id = 'c'\n"
        "skill_id = 'd'\n"
        "skill_id = 'e'\n"
    )
    git = _RegressionGit(tmp_path, {"base-sha": {"engine.py": baseline_content}})
    judge = _judge(git)
    cust = [
        CustomizationEntry(
            name="sys.skill_id variable",
            files=["*.py"],
            verification=[
                CustomizationVerification(
                    type="grep_count_baseline",
                    pattern="skill_id",
                    files=["*.py"],
                )
            ],
        )
    ]
    violations = judge.verify_customizations(cust, merge_base="base-sha")
    assert len(violations) == 1
    assert violations[0].verification_type == "grep_count_baseline"


# ─── Regression M5: CI workflow line retention violation ──────────────────────


def test_regression_m5_ci_workflow_lines_lost(tmp_path):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text("name: CI\non: [push]\n")
    baseline = (
        "name: CI\n"
        "on: [push]\n"
        "jobs:\n"
        "  dispatch_i18n_bridge:\n"
        "    runs-on: ubuntu-latest\n"
    )
    git = _RegressionGit(tmp_path, {"base-sha": {".github/workflows/ci.yml": baseline}})
    judge = _judge(git)
    cust = [
        CustomizationEntry(
            name="i18n bridge workflow",
            files=[".github/workflows/ci.yml"],
            verification=[
                CustomizationVerification(
                    type="line_retention",
                    files=[".github/workflows/ci.yml"],
                    retention_ratio=0.9,
                )
            ],
        )
    ]
    violations = judge.verify_customizations(cust, merge_base="base-sha")
    assert len(violations) == 1
    assert violations[0].verification_type == "line_retention"


# ─── Regression: enum -> registry key propagation ─────────────────────────────


def test_regression_cross_layer_enum_to_registry(tmp_path):
    (tmp_path / "types.ts").write_text(
        "enum BlockEnum {\n"
        "  Start = 'Start',\n"
        "  End = 'End',\n"
        "  NewFeatureNode = 'NewFeatureNode',\n"
        "}\n"
    )
    (tmp_path / "components.ts").write_text("Start, End\n")

    config = MergeConfig(
        upstream_ref="upstream/main",
        fork_ref="feature/fork",
        repo_path=str(tmp_path),
        cross_layer_assertions=[
            CrossLayerAssertion(
                name="BlockEnum -> NodeComponentMap",
                keys_from=r"types.ts::^\s+(\w+)\s*=\s*'",
                keys_in=["components.ts"],
                allow_missing=["IterationStart", "LoopStart", "LoopEnd"],
            )
        ],
    )
    state = MergeState(config=config)
    state.merge_base_commit = "base-sha"

    class _Stub:
        def __init__(self, repo):
            self.repo_path = repo

    judge = _judge(_Stub(tmp_path))
    view = ReadOnlyStateView(state)
    issues = judge._check_cross_layer_assertions(view)
    assert any(i.issue_type == "cross_layer_assertion_missing" for i in issues)
    first = next(i for i in issues if i.issue_type == "cross_layer_assertion_missing")
    assert "NewFeatureNode" in first.description


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
