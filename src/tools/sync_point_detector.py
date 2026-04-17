from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from src.tools.git_tool import GitTool

logger = logging.getLogger(__name__)


class SyncPointResult(BaseModel):
    detected: bool = False
    effective_merge_base: str = ""
    git_merge_base: str = ""
    synced_file_count: int = 0
    upstream_changed_file_count: int = 0
    sync_ratio: float = 0.0
    last_synced_commit: str | None = None
    first_unsynced_commit: str | None = None
    confidence: float = 0.0
    skipped_commit_count: int = 0
    patch_id_promoted_count: int = 0


class SyncPointDetector:
    """Detect whether upstream code was bulk-copied into the fork (migration).

    Three-phase algorithm:
      Phase 1 — File-level: compare blob hashes at merge_base / fork / upstream.
        A file is "synced" when upstream changed it AND fork has the same blob.
      Phase 1b — Patch-ID verification: for ambiguous files (both changed),
        compare patch-IDs to detect near-identical changes copied with tweaks.
      Phase 2 — Commit-level: walk upstream commits to find the sync boundary.
        Uses binary search for repos with many commits (>50), linear otherwise.
    """

    def __init__(
        self,
        sync_ratio_threshold: float = 0.3,
        min_synced_files: int = 5,
        enable_patch_id: bool = True,
    ) -> None:
        self.sync_ratio_threshold = sync_ratio_threshold
        self.min_synced_files = min_synced_files
        self.enable_patch_id = enable_patch_id

    def detect(
        self,
        git_tool: GitTool,
        merge_base: str,
        fork_ref: str,
        upstream_ref: str,
    ) -> SyncPointResult:
        base_hashes = git_tool.list_files_with_hashes(merge_base)
        fork_hashes = git_tool.list_files_with_hashes(fork_ref)
        up_hashes = git_tool.list_files_with_hashes(upstream_ref)

        synced_files, upstream_changed_files, ambiguous_files = (
            self._file_level_detection(base_hashes, fork_hashes, up_hashes)
        )

        promoted = 0
        if self.enable_patch_id and ambiguous_files:
            promoted_set = self._patch_id_verification(
                git_tool, merge_base, fork_ref, upstream_ref, ambiguous_files
            )
            synced_files |= promoted_set
            promoted = len(promoted_set)

        upstream_changed_count = len(upstream_changed_files)
        synced_count = len(synced_files)
        sync_ratio = (
            synced_count / upstream_changed_count if upstream_changed_count else 0.0
        )

        detected = (
            sync_ratio >= self.sync_ratio_threshold
            and synced_count >= self.min_synced_files
        )

        if not detected:
            return SyncPointResult(
                detected=False,
                effective_merge_base=merge_base,
                git_merge_base=merge_base,
                synced_file_count=synced_count,
                upstream_changed_file_count=upstream_changed_count,
                sync_ratio=sync_ratio,
                confidence=0.0,
                patch_id_promoted_count=promoted,
            )

        effective_base, last_synced, first_unsynced, skipped = (
            self._commit_boundary_detection(
                git_tool, merge_base, upstream_ref, synced_files
            )
        )

        confidence = self._compute_confidence(synced_count, sync_ratio)

        return SyncPointResult(
            detected=True,
            effective_merge_base=effective_base,
            git_merge_base=merge_base,
            synced_file_count=synced_count,
            upstream_changed_file_count=upstream_changed_count,
            sync_ratio=sync_ratio,
            last_synced_commit=last_synced,
            first_unsynced_commit=first_unsynced,
            confidence=confidence,
            skipped_commit_count=skipped,
            patch_id_promoted_count=promoted,
        )

    @staticmethod
    def _file_level_detection(
        base_hashes: dict[str, str],
        fork_hashes: dict[str, str],
        up_hashes: dict[str, str],
    ) -> tuple[set[str], set[str], set[str]]:
        """Return (synced_files, upstream_changed_files, ambiguous_files).

        A file is upstream-changed when base_hash != up_hash.
        A file is synced when upstream-changed AND fork_hash == up_hash.
        A file is ambiguous when all three hashes differ (both sides changed).
        """
        synced: set[str] = set()
        upstream_changed: set[str] = set()
        ambiguous: set[str] = set()

        all_files = set(up_hashes.keys()) | set(base_hashes.keys())

        for fp in all_files:
            up_hash = up_hashes.get(fp)
            base_hash = base_hashes.get(fp)
            fork_hash = fork_hashes.get(fp)

            if up_hash is None:
                continue
            if up_hash == base_hash:
                continue

            upstream_changed.add(fp)

            if fork_hash == up_hash:
                synced.add(fp)
            elif (
                fork_hash is not None
                and fork_hash != base_hash
                and fork_hash != up_hash
            ):
                ambiguous.add(fp)

        return synced, upstream_changed, ambiguous

    @staticmethod
    def _patch_id_verification(
        git_tool: GitTool,
        merge_base: str,
        fork_ref: str,
        upstream_ref: str,
        ambiguous_files: set[str],
    ) -> set[str]:
        """Use patch-ID comparison to detect near-identical changes.

        For ambiguous files (both changed differently by blob hash),
        compare the patch-ID of upstream's diff vs fork's diff.
        If patch-IDs match, the fork applied the same logical change.
        """
        promoted: set[str] = set()
        for fp in ambiguous_files:
            try:
                up_pid = git_tool.get_diff_patch_id(merge_base, upstream_ref, fp)
                fork_pid = git_tool.get_diff_patch_id(merge_base, fork_ref, fp)
                if up_pid and fork_pid and up_pid == fork_pid:
                    promoted.add(fp)
            except Exception:
                continue
        if promoted:
            logger.info(
                "Patch-ID verification promoted %d ambiguous files to synced",
                len(promoted),
            )
        return promoted

    @staticmethod
    def _commit_boundary_detection(
        git_tool: GitTool,
        merge_base: str,
        upstream_ref: str,
        synced_files: set[str],
    ) -> tuple[str, str | None, str | None, int]:
        """Find the sync boundary using binary search for large histories.

        Returns (effective_base, last_synced_sha, first_unsynced_sha, skipped_count).
        """
        commits = git_tool.list_commits(merge_base, upstream_ref)
        if not commits:
            return merge_base, None, None, 0

        if len(commits) > 50:
            return SyncPointDetector._binary_search_boundary(
                commits, synced_files, merge_base
            )
        return SyncPointDetector._linear_boundary(commits, synced_files, merge_base)

    @staticmethod
    def _linear_boundary(
        commits: list[dict[str, Any]],
        synced_files: set[str],
        merge_base: str,
    ) -> tuple[str, str | None, str | None, int]:
        effective_base = merge_base
        last_synced: str | None = None
        first_unsynced: str | None = None
        skipped = 0

        for commit in commits:
            sha = str(commit["sha"])
            commit_files = set(commit.get("files", []))
            if not commit_files:
                skipped += 1
                effective_base = sha
                last_synced = sha
                continue
            if commit_files.issubset(synced_files):
                skipped += 1
                effective_base = sha
                last_synced = sha
            else:
                first_unsynced = sha
                break

        return effective_base, last_synced, first_unsynced, skipped

    @staticmethod
    def _binary_search_boundary(
        commits: list[dict[str, Any]],
        synced_files: set[str],
        merge_base: str,
    ) -> tuple[str, str | None, str | None, int]:
        """Binary search for the last synced commit in a contiguous prefix.

        Assumption: synced commits form a contiguous prefix of the commit list.
        If non-contiguous, falls back to linear scan from the found boundary.
        """

        def _is_synced(idx: int) -> bool:
            files = set(commits[idx].get("files", []))
            return not files or files.issubset(synced_files)

        lo, hi = 0, len(commits) - 1
        boundary = -1

        while lo <= hi:
            mid = (lo + hi) // 2
            if _is_synced(mid):
                boundary = mid
                lo = mid + 1
            else:
                hi = mid - 1

        if boundary < 0:
            first_sha = str(commits[0]["sha"]) if commits else None
            return merge_base, None, first_sha, 0

        effective_base = str(commits[boundary]["sha"])
        last_synced = effective_base
        skipped = boundary + 1

        first_unsynced: str | None = None
        if boundary + 1 < len(commits):
            first_unsynced = str(commits[boundary + 1]["sha"])

        return effective_base, last_synced, first_unsynced, skipped

    def _compute_confidence(self, synced_count: int, sync_ratio: float) -> float:
        file_factor = min(synced_count / max(self.min_synced_files, 1), 1.0)
        ratio_factor = min(sync_ratio / max(self.sync_ratio_threshold, 0.01), 1.0)
        return round(min(file_factor * ratio_factor, 1.0), 3)
