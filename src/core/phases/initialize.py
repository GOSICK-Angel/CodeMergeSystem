from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from src.core.phases.base import Phase, PhaseContext, PhaseOutcome
from src.models.diff import (
    FileDiff,
    FileChangeCategory,
    FileStatus,
    RiskLevel,
)
from src.models.state import MergeState, SystemStatus
from src.tools.diff_parser import build_file_diff, detect_language
from src.tools.file_classifier import (
    classify_all_files,
    classify_file,
    category_summary,
    compute_risk_score,
    is_security_sensitive,
)
from src.tools.pollution_auditor import PollutionAuditor
from src.tools.config_drift_detector import ConfigDriftDetector

logger = logging.getLogger(__name__)


def _parse_file_status(status_char: str) -> FileStatus:
    mapping = {
        "A": FileStatus.ADDED,
        "M": FileStatus.MODIFIED,
        "D": FileStatus.DELETED,
        "R": FileStatus.RENAMED,
    }
    return mapping.get(status_char.upper(), FileStatus.MODIFIED)


class InitializePhase(Phase):
    name = "initialize"

    async def execute(self, state: MergeState, ctx: PhaseContext) -> PhaseOutcome:
        await asyncio.to_thread(self._run_sync, state, ctx)
        ctx.state_machine.transition(
            state, SystemStatus.PLANNING, "initialization complete"
        )
        return PhaseOutcome(
            target_status=SystemStatus.PLANNING,
            reason="initialization complete",
        )

    def _run_sync(self, state: MergeState, ctx: PhaseContext) -> None:
        ctx.notify("orchestrator", "Computing merge base")
        merge_base = ctx.git_tool.get_merge_base(
            state.config.upstream_ref, state.config.fork_ref
        )
        object.__setattr__(state, "_merge_base", merge_base)
        state.merge_base_commit = merge_base

        ctx.notify("orchestrator", "Classifying files (three-way)")
        file_categories = classify_all_files(
            merge_base,
            state.config.fork_ref,
            state.config.upstream_ref,
            ctx.git_tool,
        )

        ctx.notify("orchestrator", f"Classified {len(file_categories)} files")
        auditor = PollutionAuditor(ctx.git_tool)
        pollution_report = auditor.audit(
            merge_base,
            state.config.fork_ref,
            state.config.upstream_ref,
            file_categories,
        )
        state.pollution_audit = pollution_report
        if pollution_report.has_pollution:
            logger.info(
                "Pollution audit: %d files reclassified from %d prior merge commits",
                pollution_report.reclassified_count,
                len(pollution_report.prior_merge_commits),
            )
            file_categories = auditor.apply_corrections(
                file_categories, pollution_report
            )

        state.file_categories = file_categories

        cat_counts = category_summary(file_categories)
        logger.info(
            "Three-way classification: A=%d B=%d C=%d D-missing=%d D-extra=%d E=%d",
            cat_counts.get("unchanged", 0),
            cat_counts.get("upstream_only", 0),
            cat_counts.get("both_changed", 0),
            cat_counts.get("upstream_new", 0),
            cat_counts.get("current_only", 0),
            cat_counts.get("current_only_change", 0),
        )

        actionable_categories = {
            FileChangeCategory.B,
            FileChangeCategory.C,
            FileChangeCategory.D_MISSING,
        }
        actionable_paths = {
            fp for fp, cat in file_categories.items() if cat in actionable_categories
        }

        ctx.notify(
            "orchestrator",
            f"Building diffs for {len(actionable_paths)} actionable files",
        )
        changed_files = ctx.git_tool.get_changed_files(
            merge_base, state.config.fork_ref
        )
        file_diffs: list[FileDiff] = []

        changed_paths_map: dict[str, str] = {fp: sc for sc, fp in changed_files}

        for file_path in sorted(actionable_paths):
            status_char = changed_paths_map.get(file_path, "M")
            cat = file_categories[file_path]

            if cat == FileChangeCategory.D_MISSING:
                file_status = FileStatus.ADDED
                raw_diff = ""
            else:
                raw_diff = ctx.git_tool.get_unified_diff(
                    merge_base, state.config.fork_ref, file_path
                )
                file_status = _parse_file_status(status_char)

            language = detect_language(file_path)
            fd = build_file_diff(file_path, raw_diff, file_status)
            sensitive = is_security_sensitive(file_path, state.config.file_classifier)
            fd = fd.model_copy(
                update={
                    "language": language,
                    "is_security_sensitive": sensitive,
                    "change_category": cat,
                }
            )
            score = compute_risk_score(fd, state.config.file_classifier)
            fd = fd.model_copy(update={"risk_score": score})
            risk_level = classify_file(fd, state.config.file_classifier)
            fd = fd.model_copy(update={"risk_level": risk_level})
            file_diffs.append(fd)

        object.__setattr__(state, "_file_diffs", file_diffs)

        drift_detector = ConfigDriftDetector(Path(state.config.repo_path).resolve())
        env_files, docker_env_files = drift_detector.find_env_files()
        if env_files or docker_env_files:
            drift_report = drift_detector.detect_drift_from_files(
                env_files=env_files,
                docker_env_files=docker_env_files,
            )
            state.config_drifts = drift_report
            if drift_report.has_drifts:
                logger.info(
                    "Config drift detection: %d drifts found across %d keys",
                    drift_report.drift_count,
                    drift_report.total_keys_checked,
                )
