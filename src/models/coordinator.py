from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class CoordinatorDecision(BaseModel):
    """Routing decision returned by Coordinator for abnormal phase outcomes."""

    action: Literal["continue", "meta_review", "escalate_human"]
    reason: str
    meta_gate: str | None = Field(
        default=None,
        description="Gate ID to invoke when action='meta_review'.",
    )


class MetaReviewResult(BaseModel):
    """Advisory output produced by a meta-review LLM call.

    Stored in state.coordinator_directives and surfaced to the human
    during AWAITING_HUMAN to provide strategic context.
    """

    phase: str
    trigger: Literal["judge_stall", "plan_dispute"]
    assessment: str = Field(description="Root cause analysis, ≤ 200 chars.")
    recommendation: str = Field(description="Strategic recommendation, ≤ 200 chars.")
