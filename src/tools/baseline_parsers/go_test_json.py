"""Parser for ``go test -json`` NDJSON stream."""

from __future__ import annotations

import json

from src.tools.baseline_parsers import BaselineSnapshot, register_parser


@register_parser("go_test_json")
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
        action = rec.get("Action", "")
        pkg = rec.get("Package", "")
        test = rec.get("Test", "")
        if action == "fail" and test:
            failed_ids.add(f"{pkg}.{test}")
            failed += 1
        elif action == "pass" and test:
            passed += 1
    return {"passed": passed, "failed": failed, "failed_ids": sorted(failed_ids)}
