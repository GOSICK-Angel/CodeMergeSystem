"""Parser for TypeScript tsc --noEmit error output."""

from __future__ import annotations

import re

from src.tools.baseline_parsers import BaselineSnapshot, register_parser


_TSC_RE = re.compile(
    r"^(?P<file>[^\s(]+)\((?P<line>\d+),\d+\):\s*error\s+(?P<code>TS\d+):",
    re.MULTILINE,
)


@register_parser("tsc_errors")
def parse(output: str) -> BaselineSnapshot:
    ids: list[str] = []
    for m in _TSC_RE.finditer(output):
        ids.append(f"{m.group('file')}:{m.group('line')}:{m.group('code')}")
    failed_ids = sorted(set(ids))
    return {"passed": 0, "failed": len(failed_ids), "failed_ids": failed_ids}
