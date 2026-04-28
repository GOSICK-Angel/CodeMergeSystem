"""Memory hit tracker — observability for layered memory loader utilization.

Tracks how often the layered loader returns non-empty sections per phase
and per layer (L0 profile / L1 phase context / L2 file-relevant). Owned by
the orchestrator, passed through to ``LayeredMemoryLoader`` so all agent
calls share one counter. ``summary()`` is read at run-end by the report
writer to surface a "Memory Utilization" section.

Optionally persists each update to a sidecar JSON file so partial data
survives mid-run aborts and accumulates across resume cycles.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Literal

Layer = Literal["l0", "l1_patterns", "l1_decisions", "l2"]

_SCHEMA_VERSION = 1


class MemoryHitTracker:
    def __init__(self, persist_path: Path | None = None) -> None:
        self._lock = Lock()
        self._calls_by_phase: dict[str, int] = defaultdict(int)
        self._hit_calls_by_phase: dict[str, int] = defaultdict(int)
        self._entries_by_phase_layer: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._persist_path: Path | None = None
        if persist_path is not None:
            self.set_persist_path(persist_path)

    def set_persist_path(self, path: Path) -> None:
        with self._lock:
            self._persist_path = path
            if path.exists():
                self._load_unsafe()

    def record_call(self, phase: str, layers_with_content: dict[Layer, int]) -> None:
        with self._lock:
            self._calls_by_phase[phase] += 1
            if any(count > 0 for count in layers_with_content.values()):
                self._hit_calls_by_phase[phase] += 1
            for layer, count in layers_with_content.items():
                if count > 0:
                    self._entries_by_phase_layer[phase][layer] += count
            if self._persist_path is not None:
                self._persist_unsafe()

    def _load_unsafe(self) -> None:
        try:
            assert self._persist_path is not None
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict) or data.get("schema_version") != _SCHEMA_VERSION:
            return
        for phase, count in (data.get("calls_by_phase") or {}).items():
            self._calls_by_phase[phase] = int(count)
        for phase, count in (data.get("hit_calls_by_phase") or {}).items():
            self._hit_calls_by_phase[phase] = int(count)
        for phase, layers in (data.get("entries_by_phase_layer") or {}).items():
            for layer, count in (layers or {}).items():
                self._entries_by_phase_layer[phase][layer] = int(count)

    def _persist_unsafe(self) -> None:
        assert self._persist_path is not None
        path = self._persist_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "calls_by_phase": dict(self._calls_by_phase),
            "hit_calls_by_phase": dict(self._hit_calls_by_phase),
            "entries_by_phase_layer": {
                phase: dict(layers)
                for phase, layers in self._entries_by_phase_layer.items()
            },
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def summary(self) -> dict[str, object]:
        with self._lock:
            total_calls = sum(self._calls_by_phase.values())
            total_hit_calls = sum(self._hit_calls_by_phase.values())
            hit_rate = total_hit_calls / total_calls if total_calls > 0 else 0.0
            by_phase: dict[str, dict[str, int | float]] = {}
            for phase, calls in self._calls_by_phase.items():
                hits = self._hit_calls_by_phase.get(phase, 0)
                by_phase[phase] = {
                    "calls": calls,
                    "hit_calls": hits,
                    "hit_rate": hits / calls if calls > 0 else 0.0,
                }
            by_layer: dict[str, int] = defaultdict(int)
            for phase_layers in self._entries_by_phase_layer.values():
                for layer, count in phase_layers.items():
                    by_layer[layer] += count
            return {
                "total_calls": total_calls,
                "hit_calls": total_hit_calls,
                "hit_rate": hit_rate,
                "by_phase": by_phase,
                "by_layer": dict(by_layer),
            }
