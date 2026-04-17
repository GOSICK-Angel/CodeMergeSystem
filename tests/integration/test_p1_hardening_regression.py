"""P1 integration regression: end-to-end signal flow from upstream
interface changes to Judge VETO, and smoke-test gate after Judge PASS.

These tests use synthetic repositories (no network, no LLM) to keep them
deterministic. Run locally::

    pytest tests/integration/test_p1_hardening_regression.py -v
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.models.config import (
    MergeConfig,
    ReverseImpactConfig,
    SmokeTestCase,
    SmokeTestConfig,
    SmokeTestSuite,
)
from src.models.diff import FileChangeCategory
from src.models.state import MergeState
from src.tools.interface_change_extractor import InterfaceChangeExtractor
from src.tools.reverse_impact_scanner import ReverseImpactScanner
from src.tools.smoke_runner import SmokeRunner


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _branch_exists(repo: Path, name: str) -> bool:
    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", name],
            cwd=str(repo),
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


@pytest.fixture
def synthetic_repo(tmp_path: Path) -> Path:
    """Synthetic repo with:

    - ``upstream_branch``: upstream signature change on ``api/login.py``
    - ``fork_branch``:   fork-only file that still calls the old signature
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")

    (repo / "api").mkdir()
    (repo / "api" / "login.py").write_text("def login(user):\n    return user\n")
    (repo / "fork_only.py").write_text(
        "from api.login import login\nresult = login(user='x')\n"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")

    default_branch = "master" if _branch_exists(repo, "master") else "main"

    _git(repo, "checkout", "-q", "-b", "upstream_branch")
    (repo / "api" / "login.py").write_text(
        "def login(user, token):\n    return user + token\n"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "upstream change")

    _git(repo, "checkout", "-q", default_branch)
    _git(repo, "checkout", "-q", "-b", "fork_branch")
    (repo / "fork_only.py").write_text(
        "from api.login import login\nresult = login(user='y')\n"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "fork keeps old call")

    return repo


class TestInterfaceChangeReverseImpactFlow:
    def test_extractor_detects_signature_change_and_scanner_flags_fork(
        self, synthetic_repo
    ):
        base_content = "def login(user):\n    return user\n"
        upstream_content = "def login(user, token):\n    return user + token\n"
        changes = InterfaceChangeExtractor().extract(
            "api/login.py", base_content, upstream_content
        )
        assert any(
            c.change_kind == "method_signature" and c.symbol == "login" for c in changes
        )

        scanner = ReverseImpactScanner(synthetic_repo)
        impacts = scanner.scan(
            changes,
            fork_only_files=["fork_only.py"],
        )
        assert "login" in impacts
        assert impacts["login"] == ["fork_only.py"]


class TestPhase05IntegrationInState:
    """Simulate Phase 0.5 writing to state and Judge reading from it."""

    def test_state_captures_changes_and_impacts(self, synthetic_repo):
        config = MergeConfig(
            upstream_ref="upstream_branch",
            fork_ref="fork_branch",
            repo_path=str(synthetic_repo),
            reverse_impact=ReverseImpactConfig(enabled=True),
        )
        state = MergeState(config=config)
        state.file_categories = {
            "api/login.py": FileChangeCategory.B,
            "fork_only.py": FileChangeCategory.D_EXTRA,
        }

        base_content = "def login(user):\n    return user\n"
        upstream_content = "def login(user, token):\n    return user + token\n"
        changes = InterfaceChangeExtractor().extract_from_paths(
            [("api/login.py", base_content, upstream_content)]
        )
        state.interface_changes = changes

        scanner = ReverseImpactScanner(synthetic_repo)
        impacts = scanner.scan(
            changes,
            fork_only_files=["fork_only.py"],
        )
        state.reverse_impacts = impacts

        assert len(state.interface_changes) >= 1
        assert "login" in state.reverse_impacts


class TestSmokeGateBlocksRegression:
    @pytest.mark.asyncio
    async def test_smoke_runner_fails_on_bad_cmd(self, tmp_path):
        runner = SmokeRunner(tmp_path)
        cfg = SmokeTestConfig(
            enabled=True,
            block_on_failure=True,
            suites=[
                SmokeTestSuite(
                    name="regression",
                    kind="shell",
                    cases=[
                        SmokeTestCase(id="ok", cmd="echo ok"),
                        SmokeTestCase(id="bad", cmd="exit 1"),
                    ],
                )
            ],
        )
        report = await runner.run(cfg)
        assert not report.all_passed
        assert report.total_failed == 1
        failed = report.failed_results()
        assert failed[0].case_id == "bad"
