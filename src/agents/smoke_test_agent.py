"""P1-3: SmokeTestAgent — post-judge smoke test driver.

Thin Executor-variant agent that runs ``SmokeRunner`` using the config-supplied
suite definitions. Writes the resulting report into ``state.smoke_test_report``.

Unlike the LLM-driven agents, SmokeTestAgent performs no model calls — it
inherits from ``BaseAgent`` only to fit the agent registry and receive a
credential-free ``AgentLLMConfig`` for uniform construction.
"""

from __future__ import annotations

from pathlib import Path

import logging

from src.models.config import AgentLLMConfig
from src.models.message import AgentMessage, AgentType, MessageType
from src.models.plan import MergePhase
from src.models.smoke import SmokeTestReport
from src.models.state import MergeState
from src.tools.smoke_runner import SmokeRunner


class SmokeTestAgent:
    """Non-LLM agent that runs the smoke test suite.

    Deliberately does NOT inherit from BaseAgent — smoke execution requires
    no credentials and must be usable in test environments without API keys.
    """

    agent_type = AgentType.ORCHESTRATOR

    def __init__(self, llm_config: AgentLLMConfig, repo_path: str | None = None):
        self.llm_config = llm_config
        self._repo_path = repo_path
        self.logger = logging.getLogger("agent.smoke_test")

    async def run(self, state: MergeState) -> AgentMessage:
        cfg = state.config.smoke_tests
        repo_path = self._repo_path or state.config.repo_path
        runner = SmokeRunner(Path(repo_path).resolve())

        report: SmokeTestReport
        if not cfg.enabled or not cfg.suites:
            report = SmokeTestReport(all_passed=True, suites=[])
        else:
            report = await runner.run(cfg)

        state.smoke_test_report = report
        if not report.all_passed:
            state.consecutive_smoke_failures += 1
        else:
            state.consecutive_smoke_failures = 0

        return AgentMessage(
            sender=AgentType.ORCHESTRATOR,
            receiver=AgentType.ORCHESTRATOR,
            phase=MergePhase.JUDGE_REVIEW,
            message_type=MessageType.PHASE_COMPLETED,
            subject=(
                "smoke tests passed"
                if report.all_passed
                else f"smoke tests failed ({report.total_failed}/{report.total_cases})"
            ),
            payload={"report": report.model_dump(mode="json")},
        )

    def can_handle(self, state: MergeState) -> bool:
        return bool(state.judge_verdict) and state.config.smoke_tests.enabled
