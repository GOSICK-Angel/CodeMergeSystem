"""Parser for JUnit / Surefire XML reports."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from src.tools.baseline_parsers import BaselineSnapshot, register_parser


@register_parser("junit_xml")
def parse(output: str) -> BaselineSnapshot:
    try:
        root = ET.fromstring(output)
    except ET.ParseError:
        return {"passed": 0, "failed": 0, "failed_ids": []}

    failed_ids: list[str] = []
    passed = 0
    failed = 0

    for testcase in root.iter("testcase"):
        classname = testcase.get("classname", "")
        name = testcase.get("name", "")
        test_id = f"{classname}.{name}" if classname else name

        has_failure = any(child.tag in ("failure", "error") for child in testcase)
        has_skip = any(child.tag == "skipped" for child in testcase)
        if has_failure:
            failed += 1
            if test_id:
                failed_ids.append(test_id)
        elif not has_skip:
            passed += 1

    return {"passed": passed, "failed": failed, "failed_ids": sorted(set(failed_ids))}
