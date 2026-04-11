"""Three-layer memory loading: L0 (profile), L1 (phase essentials), L2 (file-relevant)."""

from __future__ import annotations

from src.memory.store import MemoryStore

L1_MAX_PATTERNS = 5
L1_MAX_DECISIONS = 5
L2_MAX_ENTRIES = 8

_PHASE_ORDER = ["planning", "auto_merge", "conflict_analysis", "judge_review"]


class LayeredMemoryLoader:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def load_for_agent(
        self,
        current_phase: str,
        file_paths: list[str] | None = None,
    ) -> str:
        sections: list[str] = []

        l0 = self._build_l0()
        if l0:
            sections.append(l0)

        l1 = self._build_l1(current_phase)
        if l1:
            sections.append(l1)

        if file_paths:
            l2 = self._build_l2(file_paths)
            if l2:
                sections.append(l2)

        return "\n\n".join(sections) if sections else ""

    def _build_l0(self) -> str:
        profile = self._store.codebase_profile
        if not profile:
            return ""
        lines = [f"- {k}: {v}" for k, v in profile.items()]
        return "## Project Profile\n" + "\n".join(lines)

    def _build_l1(self, current_phase: str) -> str:
        parts: list[str] = []

        current_summary = self._store.get_phase_summary(current_phase)
        if current_summary and current_summary.patterns_discovered:
            patterns = current_summary.patterns_discovered[:L1_MAX_PATTERNS]
            parts.append("Key patterns: " + "; ".join(patterns))

        prev_phase = _previous_phase(current_phase)
        if prev_phase:
            prev_summary = self._store.get_phase_summary(prev_phase)
            if prev_summary and prev_summary.key_decisions:
                decisions = prev_summary.key_decisions[:L1_MAX_DECISIONS]
                parts.append("Prior phase decisions: " + "; ".join(decisions))

        if not parts:
            return ""
        return "## Phase Context\n" + "\n".join(parts)

    def _build_l2(self, file_paths: list[str]) -> str:
        relevant = self._store.get_relevant_context(
            file_paths, max_entries=L2_MAX_ENTRIES
        )
        if not relevant:
            return ""

        lines: list[str] = []
        for entry in relevant:
            if not _has_path_overlap(entry.file_paths, file_paths):
                continue
            label = entry.confidence_level.value.upper()
            lines.append(f"- [{label}] {entry.content}")

        if not lines:
            return ""
        return "## Relevant Patterns\n" + "\n".join(lines)


def _previous_phase(phase: str) -> str | None:
    try:
        idx = _PHASE_ORDER.index(phase)
        return _PHASE_ORDER[idx - 1] if idx > 0 else None
    except ValueError:
        return None


def _has_path_overlap(entry_paths: list[str], query_paths: list[str]) -> bool:
    if not entry_paths:
        return True
    for ep in entry_paths:
        for qp in query_paths:
            if ep == qp or ep.startswith(qp) or qp.startswith(ep):
                return True
    return False
