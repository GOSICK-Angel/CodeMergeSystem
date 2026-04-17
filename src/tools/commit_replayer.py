from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.models.diff import FileChangeCategory
from src.models.state import MergeState
from src.tools.git_tool import GitTool

logger = logging.getLogger(__name__)

REPLAYABLE_CATEGORIES = frozenset({FileChangeCategory.B, FileChangeCategory.D_MISSING})


@dataclass
class ReplayResult:
    replayed_shas: list[str] = field(default_factory=list)
    failed_shas: list[str] = field(default_factory=list)
    replayed_files: list[str] = field(default_factory=list)


class CommitReplayer:
    def classify_commits(
        self,
        commits: list[dict[str, Any]],
        file_categories: dict[str, FileChangeCategory],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        replayable: list[dict[str, Any]] = []
        non_replayable: list[dict[str, Any]] = []

        for commit in commits:
            files: list[str] = commit.get("files", [])
            if not files:
                non_replayable.append(commit)
                continue

            all_clean = all(
                file_categories.get(f) in REPLAYABLE_CATEGORIES for f in files
            )
            if all_clean:
                replayable.append(commit)
            else:
                non_replayable.append(commit)

        return replayable, non_replayable

    async def replay_clean_commits(
        self,
        git_tool: GitTool,
        replayable: list[dict[str, Any]],
        state: MergeState,
    ) -> ReplayResult:
        result = ReplayResult()

        for commit in replayable:
            sha: str = commit["sha"]
            ok = git_tool.cherry_pick(sha)
            if ok:
                result.replayed_shas.append(sha)
                commit_files: list[str] = commit.get("files", [])
                result.replayed_files.extend(commit_files)
                logger.info(
                    "Cherry-picked %s: %s (%d files)",
                    sha[:8],
                    commit.get("message", ""),
                    len(commit_files),
                )
            else:
                git_tool.cherry_pick_abort()
                result.failed_shas.append(sha)
                logger.warning(
                    "Cherry-pick failed for %s: %s — will fall back to apply",
                    sha[:8],
                    commit.get("message", ""),
                )

        state.replayed_commits = list(result.replayed_shas)
        state.replayed_files = list(result.replayed_files)
        return result

    def collect_upstream_messages(
        self,
        git_tool: GitTool,
        merge_base: str,
        upstream_ref: str,
        files: list[str],
    ) -> str:
        seen: set[str] = set()
        lines: list[str] = []
        for fp in files:
            msgs = git_tool.get_commit_messages(fp, upstream_ref, limit=5)
            for msg in msgs:
                if msg not in seen:
                    seen.add(msg)
                    lines.append(f"- {msg}")
        return "\n".join(lines)
