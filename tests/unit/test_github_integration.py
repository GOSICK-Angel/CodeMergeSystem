from datetime import datetime

import pytest

from src.integrations.github_client import GitHubClient, ReviewComment
from src.integrations.github_formatter import (
    format_decision_request_as_comment,
    format_summary_comment,
    parse_decision_from_comment,
)
from src.models.config import GitHubConfig
from src.models.decision import MergeDecision
from src.models.human import DecisionOption, HumanDecisionRequest


def _make_request(file_path: str = "src/main.py") -> HumanDecisionRequest:
    return HumanDecisionRequest(
        file_path=file_path,
        priority=5,
        conflict_points=[],
        context_summary="File has conflicts",
        upstream_change_summary="Added 10 lines",
        fork_change_summary="Deleted 5 lines",
        analyst_recommendation=MergeDecision.TAKE_TARGET,
        analyst_confidence=0.75,
        analyst_rationale="Upstream version is preferred",
        options=[
            DecisionOption(
                option_key="A",
                decision=MergeDecision.TAKE_CURRENT,
                description="Keep fork",
            ),
            DecisionOption(
                option_key="B",
                decision=MergeDecision.TAKE_TARGET,
                description="Take upstream",
            ),
            DecisionOption(
                option_key="C",
                decision=MergeDecision.SEMANTIC_MERGE,
                description="Merge both",
            ),
        ],
        created_at=datetime.now(),
    )


class TestGitHubFormatter:
    def test_format_comment_contains_file_path(self) -> None:
        req = _make_request("src/app.py")
        comment = format_decision_request_as_comment(req)
        assert comment.path == "src/app.py"

    def test_format_comment_contains_options(self) -> None:
        req = _make_request()
        comment = format_decision_request_as_comment(req)
        assert "/take_current" in comment.body
        assert "/take_target" in comment.body

    def test_format_comment_contains_recommendation(self) -> None:
        req = _make_request()
        comment = format_decision_request_as_comment(req)
        assert "take_target" in comment.body
        assert "75%" in comment.body

    def test_format_summary(self) -> None:
        reqs = [_make_request("a.py"), _make_request("b.py")]
        summary = format_summary_comment(reqs)
        assert "2 files" in summary
        assert "a.py" in summary
        assert "b.py" in summary


class TestParseDecision:
    def test_parse_take_target(self) -> None:
        assert parse_decision_from_comment("/take_target") == MergeDecision.TAKE_TARGET

    def test_parse_take_current(self) -> None:
        assert (
            parse_decision_from_comment("/take_current") == MergeDecision.TAKE_CURRENT
        )

    def test_parse_semantic_merge(self) -> None:
        assert (
            parse_decision_from_comment("/semantic_merge")
            == MergeDecision.SEMANTIC_MERGE
        )

    def test_parse_with_surrounding_text(self) -> None:
        body = "I think we should\n/take_target\nfor this file"
        assert parse_decision_from_comment(body) == MergeDecision.TAKE_TARGET

    def test_parse_no_decision(self) -> None:
        assert parse_decision_from_comment("just a regular comment") is None

    def test_parse_invalid_decision(self) -> None:
        assert parse_decision_from_comment("/not_a_decision") is None

    def test_parse_skip(self) -> None:
        assert parse_decision_from_comment("/skip") == MergeDecision.SKIP


class TestGitHubConfig:
    def test_defaults(self) -> None:
        cfg = GitHubConfig()
        assert cfg.enabled is False
        assert cfg.token_env == "GITHUB_TOKEN"
        assert cfg.repo == ""
        assert cfg.pr_number is None

    def test_custom(self) -> None:
        cfg = GitHubConfig(enabled=True, repo="owner/repo", pr_number=42)
        assert cfg.enabled is True
        assert cfg.pr_number == 42


class TestReviewComment:
    def test_create(self) -> None:
        c = ReviewComment(path="foo.py", body="test")
        assert c.path == "foo.py"
        assert c.side == "RIGHT"

    def test_with_line(self) -> None:
        c = ReviewComment(path="foo.py", body="test", line=42)
        assert c.line == 42


class TestGitHubClient:
    def test_init(self) -> None:
        client = GitHubClient(token="test-token", repo="owner/repo")
        assert client.repo == "owner/repo"
        assert "token test-token" in client._headers["Authorization"]
