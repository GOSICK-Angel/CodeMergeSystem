from __future__ import annotations

from src.agents.base_agent import BaseAgent
from src.models.config import AgentLLMConfig
from src.models.message import AgentType, AgentMessage, MessageType
from src.models.plan import MergePlan, MergePhase
from src.models.diff import FileDiff
from src.models.plan_judge import PlanIssue, PlanJudgeVerdict
from src.models.state import MergeState
from src.llm.prompts.planner_judge_prompts import (
    get_planner_judge_system,
    build_plan_review_prompt,
)
from src.models.plan_review import PlannerIssueResponse
from src.llm.response_parser import parse_plan_judge_verdict


class PlannerJudgeAgent(BaseAgent):
    agent_type = AgentType.PLANNER_JUDGE
    contract_name = "planner_judge"

    def __init__(self, llm_config: AgentLLMConfig):
        super().__init__(llm_config)

    async def run(self, state: MergeState) -> AgentMessage:
        view = self.restricted_view(state)
        if view.merge_plan is None:
            raise ValueError("No merge plan to review")

        file_diffs: list[FileDiff] = view.file_diffs

        lang = view.config.output.language
        verdict = await self.review_plan(view.merge_plan, file_diffs, 0, lang=lang)

        return AgentMessage(
            sender=AgentType.PLANNER_JUDGE,
            receiver=AgentType.ORCHESTRATOR,
            phase=MergePhase.PLAN_REVIEW,
            message_type=MessageType.PHASE_COMPLETED,
            subject="Plan review completed",
            payload={"verdict": verdict.model_dump(mode="json")},
        )

    async def review_plan(
        self,
        plan: MergePlan,
        file_diffs: list[FileDiff],
        revision_round: int,
        lang: str = "en",
        *,
        prior_resolved: list[PlanIssue] | None = None,
        prior_still_open: list[PlanIssue] | None = None,
        planner_responses: list[PlannerIssueResponse] | None = None,
    ) -> PlanJudgeVerdict:
        prompt = build_plan_review_prompt(
            plan,
            file_diffs,
            lang=lang,
            revision_round=revision_round,
            prior_resolved=prior_resolved,
            prior_still_open=prior_still_open,
            planner_responses=planner_responses,
        )

        messages = [{"role": "user", "content": prompt}]

        system = get_planner_judge_system(lang)
        try:
            raw = await self._call_llm_with_retry(
                messages, system=system, json_mode=True
            )
            return parse_plan_judge_verdict(
                str(raw), self.llm_config.model, revision_round
            )
        except Exception as e:
            self.logger.error("Plan review failed: %s", e)
            from src.models.plan_judge import PlanJudgeResult
            from datetime import datetime

            error_type = type(e).__name__
            is_llm_unavailable = any(
                marker in error_type
                for marker in ("AgentExhaustedError", "APIError", "RateLimitError")
            ) or any(
                marker in str(e)
                for marker in ("LLM call failed", "502", "503", "No available accounts")
            )
            result = (
                PlanJudgeResult.LLM_UNAVAILABLE
                if is_llm_unavailable
                else PlanJudgeResult.REVISION_NEEDED
            )
            summary_prefix = (
                "Plan Judge LLM unavailable"
                if is_llm_unavailable
                else f"Review parse failed ({error_type})"
            )
            return PlanJudgeVerdict(
                result=result,
                revision_round=revision_round,
                issues=[],
                approved_files_count=0,
                flagged_files_count=0,
                summary=f"{summary_prefix}: {str(e)[:200]}",
                judge_model=self.llm_config.model,
                timestamp=datetime.now(),
            )

    def can_handle(self, state: MergeState) -> bool:
        from src.models.state import SystemStatus

        return state.status == SystemStatus.PLAN_REVIEWING


from src.agents.registry import AgentRegistry  # noqa: E402

AgentRegistry.register("planner_judge", PlannerJudgeAgent)
