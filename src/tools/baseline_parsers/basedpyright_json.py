"""Parser for basedpyright / pyright JSON output."""

from __future__ import annotations

import json

from src.tools.baseline_parsers import BaselineSnapshot, register_parser


@register_parser("basedpyright_json")
def parse(output: str) -> BaselineSnapshot:
    try:
        data = json.loads(output)
    except (ValueError, TypeError):
        return {"passed": 0, "failed": 0, "failed_ids": []}

    diagnostics = data.get("generalDiagnostics") or []
    failed_ids: list[str] = []
    for d in diagnostics:
        if d.get("severity") != "error":
            continue
        fp = d.get("file", "")
        rng = d.get("range", {}).get("start", {})
        line = rng.get("line", 0)
        failed_ids.append(f"{fp}:{line}")

    summary = data.get("summary") or {}
    failed = int(summary.get("errorCount", len(failed_ids)))
    return {"passed": 0, "failed": failed, "failed_ids": sorted(set(failed_ids))}
