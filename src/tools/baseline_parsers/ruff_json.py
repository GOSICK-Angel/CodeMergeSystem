"""Parser for ruff --output-format=json output."""

from __future__ import annotations

import json

from src.tools.baseline_parsers import BaselineSnapshot, register_parser


@register_parser("ruff_json")
def parse(output: str) -> BaselineSnapshot:
    try:
        data = json.loads(output)
    except (ValueError, TypeError):
        return {"passed": 0, "failed": 0, "failed_ids": []}

    if not isinstance(data, list):
        return {"passed": 0, "failed": 0, "failed_ids": []}

    failed_ids: list[str] = []
    for d in data:
        fp = d.get("filename", "")
        loc = d.get("location") or {}
        row = loc.get("row", 0)
        code = d.get("code", "")
        failed_ids.append(f"{fp}:{row}:{code}")

    return {
        "passed": 0,
        "failed": len(failed_ids),
        "failed_ids": sorted(set(failed_ids)),
    }
