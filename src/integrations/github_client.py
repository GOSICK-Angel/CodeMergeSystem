from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ReviewComment(BaseModel):
    path: str
    line: int | None = None
    body: str
    side: str = "RIGHT"


class GitHubClient:
    """GitHub API client for PR review operations."""

    def __init__(self, token: str, repo: str) -> None:
        self.token = token
        self.repo = repo
        self.base_url = "https://api.github.com"
        self._headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    async def create_review(
        self, pr_number: int, comments: list[ReviewComment], body: str = ""
    ) -> dict[str, Any]:
        """Create a PR review with comments."""
        import httpx

        url = f"{self.base_url}/repos/{self.repo}/pulls/{pr_number}/reviews"
        payload: dict[str, Any] = {
            "body": body,
            "event": "COMMENT",
            "comments": [
                {
                    "path": c.path,
                    "body": c.body,
                    "side": c.side,
                    **({"line": c.line} if c.line is not None else {"position": 1}),
                }
                for c in comments
            ],
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url, json=payload, headers=self._headers, timeout=30.0
            )
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result

    async def get_review_comments(self, pr_number: int) -> list[dict[str, Any]]:
        """Get all review comments on a PR."""
        import httpx

        url = f"{self.base_url}/repos/{self.repo}/pulls/{pr_number}/comments"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers, timeout=30.0)
            resp.raise_for_status()
            result: list[dict[str, Any]] = resp.json()
            return result

    async def add_comment(self, pr_number: int, body: str) -> dict[str, Any]:
        """Add a general comment to a PR."""
        import httpx

        url = f"{self.base_url}/repos/{self.repo}/issues/{pr_number}/comments"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={"body": body},
                headers=self._headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
