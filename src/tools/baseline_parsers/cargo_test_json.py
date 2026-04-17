"""Parser for ``cargo test -- --format json`` NDJSON stream."""

from __future__ import annotations

import json

from src.tools.baseline_parsers import BaselineSnapshot, register_parser


@register_parser("cargo_test_json")
def parse(output: str) -> BaselineSnapshot:
    failed_ids: set[str] = set()
    passed = 0
    failed = 0
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if rec.get("type") != "test":
            continue
        event = rec.get("event", "")
        name = rec.get("name", "")
        if event == "failed" and name:
            failed_ids.add(name)
            failed += 1
        elif event == "ok" and name:
            passed += 1
    return {"passed": passed, "failed": failed, "failed_ids": sorted(failed_ids)}
