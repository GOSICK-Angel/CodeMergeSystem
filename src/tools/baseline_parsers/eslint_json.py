"""Parser for ESLint --format json output."""

from __future__ import annotations

import json

from src.tools.baseline_parsers import BaselineSnapshot, register_parser


@register_parser("eslint_json")
def parse(output: str) -> BaselineSnapshot:
    try:
        data = json.loads(output)
    except (ValueError, TypeError):
        return {"passed": 0, "failed": 0, "failed_ids": []}

    if not isinstance(data, list):
        return {"passed": 0, "failed": 0, "failed_ids": []}

    failed_ids: list[str] = []
    for entry in data:
        fp = entry.get("filePath", "")
        for msg in entry.get("messages") or []:
            if msg.get("severity", 0) < 2:
                continue
            line = msg.get("line", 0)
            rule = msg.get("ruleId") or "error"
            failed_ids.append(f"{fp}:{line}:{rule}")

    return {
        "passed": 0,
        "failed": len(failed_ids),
        "failed_ids": sorted(set(failed_ids)),
    }
