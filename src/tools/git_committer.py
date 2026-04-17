from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.models.state import MergeState
from src.tools.git_tool import GitTool

logger = logging.getLogger(__name__)


class GitCommitter:
    def commit_phase_changes(
        self,
        git_tool: GitTool,
        state: MergeState,
        phase_name: str,
        file_paths: list[str],
        upstream_context: str = "",
    ) -> str | None:
        committable = [
            fp
            for fp in file_paths
            if (git_tool.repo_path / fp).exists() and fp not in state.replayed_files
        ]
        if not committable:
            return None

        git_tool.stage_files(committable)

        if not git_tool.has_staged_changes():
            return None

        message = f"merge({phase_name}): resolve {len(committable)} files"
        if upstream_context:
            message += f"\n\nUpstream commits:\n{upstream_context}"

        sha = git_tool.commit_staged(message)

        entry: dict[str, Any] = {
            "phase": phase_name,
            "commit_sha": sha,
            "files": committable,
            "timestamp": datetime.now().isoformat(),
        }
        state.merge_commit_log.append(entry)

        logger.info(
            "Committed %s: %d files in phase %s",
            sha[:8],
            len(committable),
            phase_name,
        )
        return sha
