"""Smart model routing (D1).

Automatically selects a cheaper model for trivial tasks (short messages,
no code, simple confirmations) while using the primary model for complex
reasoning.  Inspired by Hermes ``smart_model_routing.py``.

The router is **opt-in**: it only activates when ``AgentLLMConfig.cheap_model``
is set.  Callers may also force a complexity level to bypass heuristics.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from src.models.config import AgentLLMConfig


class TaskComplexity(str, Enum):
    TRIVIAL = "trivial"
    STANDARD = "standard"
    COMPLEX = "complex"


# Heuristic thresholds (aligned with Hermes defaults)
_MAX_TRIVIAL_CHARS = 160
_MAX_TRIVIAL_WORDS = 28
_CODE_PATTERNS = re.compile(
    r"```|def\s+\w+|class\s+\w+|function\s+\w+|import\s+|from\s+\w+\s+import"
    r"|if\s*\(|for\s*\(|while\s*\(|\{|\}|=>|->|<\w+>",
)


def classify_task_complexity(
    messages: list[dict[str, Any]],
    *,
    max_trivial_chars: int = _MAX_TRIVIAL_CHARS,
    max_trivial_words: int = _MAX_TRIVIAL_WORDS,
) -> TaskComplexity:
    """Classify the complexity of an LLM task based on message content.

    Rules:
    - TRIVIAL: last user message is short (<160 chars, <28 words) and
      contains no code-like patterns.
    - COMPLEX: total content exceeds 2000 chars or contains multiple
      code blocks / diff hunks.
    - STANDARD: everything else.
    """
    if not messages:
        return TaskComplexity.STANDARD

    last_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_content = msg.get("content", "")
            if isinstance(last_content, list):
                last_content = " ".join(
                    b.get("text", "") for b in last_content if isinstance(b, dict)
                )
            break

    if not last_content:
        return TaskComplexity.STANDARD

    total_content = " ".join(
        m.get("content", "") for m in messages if isinstance(m.get("content"), str)
    )

    code_matches = len(_CODE_PATTERNS.findall(total_content))
    if code_matches >= 5 or len(total_content) > 5000:
        return TaskComplexity.COMPLEX

    char_count = len(last_content)
    word_count = len(last_content.split())
    has_code = bool(_CODE_PATTERNS.search(last_content))

    if (
        char_count <= max_trivial_chars
        and word_count <= max_trivial_words
        and not has_code
    ):
        return TaskComplexity.TRIVIAL

    return TaskComplexity.STANDARD


def select_model(
    messages: list[dict[str, Any]],
    config: AgentLLMConfig,
    *,
    force_complexity: TaskComplexity | None = None,
) -> str:
    """Select the optimal model based on task complexity.

    Returns ``config.cheap_model`` for trivial tasks when available,
    otherwise falls back to ``config.model``.
    """
    if not config.cheap_model:
        return config.model

    complexity = force_complexity or classify_task_complexity(messages)

    if complexity == TaskComplexity.TRIVIAL:
        return config.cheap_model

    return config.model
