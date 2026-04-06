from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field

from src.models.config import GateCommandConfig

logger = logging.getLogger(__name__)


class GateResult(BaseModel):
    gate_name: str
    passed: bool
    exit_code: int
    stdout_tail: str = ""
    stderr_tail: str = ""
    duration_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)


class GateReport(BaseModel):
    all_passed: bool
    results: list[GateResult] = Field(default_factory=list)
    baseline_comparison: dict[str, str] = Field(default_factory=dict)


class GateRunner:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    async def run_gate(self, gate: GateCommandConfig) -> GateResult:
        work_dir = self.repo_path / gate.working_dir
        start = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_shell(
                gate.command,
                cwd=str(work_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=gate.timeout_seconds,
            )
            exit_code = proc.returncode if proc.returncode is not None else 0
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            logger.warning(
                "Gate '%s' timed out after %ds", gate.name, gate.timeout_seconds
            )
            return GateResult(
                gate_name=gate.name,
                passed=False,
                exit_code=-1,
                stdout_tail="",
                stderr_tail=f"Timeout after {gate.timeout_seconds}s",
                duration_seconds=time.monotonic() - start,
            )
        except Exception as exc:
            logger.error("Gate '%s' execution error: %s", gate.name, exc)
            return GateResult(
                gate_name=gate.name,
                passed=False,
                exit_code=-2,
                stderr_tail=str(exc),
                duration_seconds=time.monotonic() - start,
            )

        duration = time.monotonic() - start
        stdout_lines = stdout_str.strip().splitlines()
        stderr_lines = stderr_str.strip().splitlines()

        passed = exit_code == 0

        logger.info(
            "Gate '%s': exit=%d passed=%s (%.1fs)",
            gate.name,
            exit_code,
            passed,
            duration,
        )

        return GateResult(
            gate_name=gate.name,
            passed=passed,
            exit_code=exit_code,
            stdout_tail="\n".join(stdout_lines[-20:]),
            stderr_tail="\n".join(stderr_lines[-20:]),
            duration_seconds=round(duration, 2),
        )

    async def run_all_gates(
        self,
        gates: list[GateCommandConfig],
        baselines: dict[str, str] | None = None,
    ) -> GateReport:
        results: list[GateResult] = []
        for gate in gates:
            result = await self.run_gate(gate)

            if (
                gate.pass_criteria == "not_worse_than_baseline"
                and baselines
                and not result.passed
            ):
                baseline_output = baselines.get(gate.name)
                if baseline_output is not None:
                    baseline_failed = _extract_failed_count(baseline_output)
                    current_failed = _extract_failed_count(result.stdout_tail)
                    if (
                        baseline_failed is not None
                        and current_failed is not None
                        and current_failed <= baseline_failed
                    ):
                        result = result.model_copy(update={"passed": True})
                        logger.info(
                            "Gate '%s' failed=%d <= baseline=%d, treating as pass",
                            gate.name,
                            current_failed,
                            baseline_failed,
                        )

            results.append(result)

        comparison: dict[str, str] = {}
        if baselines:
            for result in results:
                baseline = baselines.get(result.gate_name)
                if baseline is None:
                    comparison[result.gate_name] = "no_baseline"
                elif result.passed:
                    comparison[result.gate_name] = "passed"
                else:
                    comparison[result.gate_name] = "regressed"

        all_passed = all(r.passed for r in results) if results else True

        return GateReport(
            all_passed=all_passed,
            results=results,
            baseline_comparison=comparison,
        )

    async def record_baseline(self, gates: list[GateCommandConfig]) -> dict[str, str]:
        baselines: dict[str, str] = {}
        for gate in gates:
            result = await self.run_gate(gate)
            baselines[gate.name] = result.stdout_tail
        return baselines


def _extract_failed_count(output: str) -> int | None:
    import re

    patterns = [
        r"(\d+)\s+failed",
        r"failed[:\s]+(\d+)",
        r"failures[:\s]+(\d+)",
        r"errors[:\s]+(\d+)",
        r"(\d+)\s+error",
    ]
    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None
