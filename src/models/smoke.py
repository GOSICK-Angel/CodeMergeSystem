"""P1-3: SmokeTest runtime data models.

Independent models for Phase 5.5 smoke test execution.  Kept separate from
``config.py`` to avoid circular imports — ``SmokeTestConfig`` stays in
config.py as user-facing YAML schema, while runtime result models live here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SmokeCaseStatus = Literal["pass", "fail", "skipped", "error"]


class SmokeTestResult(BaseModel):
    suite_name: str
    case_id: str
    kind: Literal["shell", "http", "playwright"]
    status: SmokeCaseStatus
    duration_seconds: float = 0.0
    exit_code: int | None = None
    http_status: int | None = None
    stderr_tail: str = ""
    stdout_tail: str = ""
    error_message: str = ""


class SmokeSuiteReport(BaseModel):
    suite_name: str
    kind: Literal["shell", "http", "playwright"]
    results: list[SmokeTestResult] = Field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.status == "pass" for r in self.results)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.status in ("fail", "error"))


class SmokeTestReport(BaseModel):
    all_passed: bool
    suites: list[SmokeSuiteReport] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)

    @property
    def total_cases(self) -> int:
        return sum(len(s.results) for s in self.suites)

    @property
    def total_failed(self) -> int:
        return sum(s.failed_count for s in self.suites)

    def failed_results(self) -> list[SmokeTestResult]:
        out: list[SmokeTestResult] = []
        for suite in self.suites:
            out.extend(r for r in suite.results if r.status in ("fail", "error"))
        return out
