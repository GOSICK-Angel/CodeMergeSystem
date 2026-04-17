"""Parser for pytest terminal summary.

Accepts standard pytest ``--tb=no -q`` output. Extracts failed test node ids
from ``FAILED tests/...::test_name`` lines and summary counts from the
final ``N failed, M passed`` line.
"""

from __future__ import annotations

import re

from src.tools.baseline_parsers import BaselineSnapshot, register_parser


_FAILED_ID_RE = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)
_PASSED_RE = re.compile(r"(\d+)\s+passed", re.IGNORECASE)
_FAILED_RE = re.compile(r"(\d+)\s+failed", re.IGNORECASE)
_ERROR_RE = re.compile(r"(\d+)\s+error", re.IGNORECASE)


@register_parser("pytest_summary")
def parse(output: str) -> BaselineSnapshot:
    failed_ids = sorted(set(_FAILED_ID_RE.findall(output)))
    passed_m = _PASSED_RE.search(output)
    failed_m = _FAILED_RE.search(output)
    error_m = _ERROR_RE.search(output)
    passed = int(passed_m.group(1)) if passed_m else 0
    failed = int(failed_m.group(1)) if failed_m else 0
    failed += int(error_m.group(1)) if error_m else 0
    return {"passed": passed, "failed": failed, "failed_ids": failed_ids}
