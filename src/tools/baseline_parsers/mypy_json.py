"""Parser for mypy text output.

mypy emits ``<file>:<line>: error: <message>`` lines followed by a
``Found N errors in M files`` summary. failed_ids are ``<file>:<line>``.
"""

from __future__ import annotations

import re

from src.tools.baseline_parsers import BaselineSnapshot, register_parser


_ERROR_RE = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):\s*error:", re.MULTILINE)
_SUMMARY_RE = re.compile(r"Found\s+(\d+)\s+errors?", re.IGNORECASE)


@register_parser("mypy_json")
def parse(output: str) -> BaselineSnapshot:
    ids: list[str] = []
    for m in _ERROR_RE.finditer(output):
        ids.append(f"{m.group('file')}:{m.group('line')}")
    failed_ids = sorted(set(ids))

    summary = _SUMMARY_RE.search(output)
    failed = int(summary.group(1)) if summary else len(failed_ids)
    return {"passed": 0, "failed": failed, "failed_ids": failed_ids}
