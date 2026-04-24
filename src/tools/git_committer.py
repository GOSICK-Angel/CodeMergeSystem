from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.models.decision import MergeDecision
from src.models.state import MergeState
from src.tools.git_tool import GitTool

logger = logging.getLogger(__name__)

_O_M2_RESOLVABLE_DECISIONS = {
    MergeDecision.TAKE_TARGET,
    MergeDecision.TAKE_CURRENT,
    MergeDecision.SEMANTIC_MERGE,
    MergeDecision.MANUAL_PATCH,
}


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

        # O-M2: handle leftover unmerged index entries (stages 1/2/3 from
        # cherry-pick fallback). Without this, `git write-tree` during commit
        # raises UnmergedEntriesError and the whole run FAILs. Strategy:
        #   - entry has a resolvable FileDecisionRecord -> force-add
        #     (working tree was written by O-L5 / main loop / executor).
        #   - entry is ESCALATE_HUMAN or no record -> drop from committable
        #     so it stays unresolved, but commit the rest.
        unmerged = set(git_tool.get_unmerged_files())
        if unmerged:
            drop: list[str] = []
            force_add: list[str] = []
            for fp in list(committable):
                if fp not in unmerged:
                    continue
                rec = state.file_decision_records.get(fp)
                decision = rec.decision if rec is not None else None
                if decision in _O_M2_RESOLVABLE_DECISIONS:
                    force_add.append(fp)
                else:
                    drop.append(fp)
            if drop:
                logger.warning(
                    "O-M2: dropping %d unmerged file(s) without resolvable "
                    "decision from commit: %s",
                    len(drop),
                    drop[:10],
                )
                committable = [fp for fp in committable if fp not in drop]
                # Clear the index stages for dropped files so that
                # write_tree still succeeds for the rest. The file stays
                # on disk (--cached); a future phase can still decide it.
                for fp in drop:
                    try:
                        git_tool.repo.git.rm("--cached", "-q", "--", fp)
                    except Exception as exc:
                        logger.warning(
                            "O-M2: failed to git rm --cached %s: %s", fp, exc
                        )
            if force_add:
                logger.info(
                    "O-M2: force-adding %d unmerged file(s) with resolved "
                    "decisions to clear index stages",
                    len(force_add),
                )
                # `git add` alone does NOT clear stage-1/2/3 entries, and
                # neither does `git update-index --remove` — they leave
                # the higher stages behind so write-tree keeps failing.
                # Only `git rm --cached -f` fully drops every stage for a
                # path. Remove first, then re-add from the working tree.
                for fp in force_add:
                    try:
                        git_tool.repo.git.rm("--cached", "-f", "-q", "--", fp)
                    except Exception as exc:
                        logger.warning(
                            "O-M2: git rm --cached -f failed for %s: %s",
                            fp,
                            exc,
                        )
                git_tool.repo.git.add("--", *force_add)

            # Files that are unmerged but not in our committable set at all
            # must also be cleared from the index (otherwise write-tree
            # still fails). Only force-add those whose working-tree content
            # exists and that have a resolvable decision; others get logged.
            leftover = unmerged - set(committable) - set(force_add) - set(drop)
            if leftover:
                rescue: list[str] = []
                stuck: list[str] = []
                for fp in leftover:
                    if not (git_tool.repo_path / fp).exists():
                        stuck.append(fp)
                        continue
                    rec = state.file_decision_records.get(fp)
                    if rec is not None and rec.decision in _O_M2_RESOLVABLE_DECISIONS:
                        rescue.append(fp)
                    else:
                        stuck.append(fp)
                if rescue:
                    logger.info(
                        "O-M2: rescuing %d unmerged file(s) not in committable "
                        "set via force-add: %s",
                        len(rescue),
                        rescue[:10],
                    )
                    for fp in rescue:
                        try:
                            git_tool.repo.git.rm("--cached", "-f", "-q", "--", fp)
                        except Exception as exc:
                            logger.warning(
                                "O-M2: git rm --cached -f failed for %s: %s",
                                fp,
                                exc,
                            )
                    git_tool.repo.git.add("--", *rescue)
                if stuck:
                    logger.warning(
                        "O-M2: %d unmerged file(s) have no resolvable "
                        "record — clearing from index via git rm --cached "
                        "so commit can proceed: %s",
                        len(stuck),
                        stuck[:10],
                    )
                    for fp in stuck:
                        try:
                            git_tool.repo.git.rm("--cached", "-q", "--", fp)
                        except Exception as exc:
                            logger.warning(
                                "O-M2: failed to git rm --cached %s: %s",
                                fp,
                                exc,
                            )

        if unmerged:
            # We manipulated the on-disk index via the CLI in O-M2 above;
            # the GitPython in-memory IndexFile must be re-read *before*
            # any subsequent GitPython index writes, otherwise they
            # overwrite our CLI changes with the stale cached state.
            git_tool.reload_index()

        if committable:
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
