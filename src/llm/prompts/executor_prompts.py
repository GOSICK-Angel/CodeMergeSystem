from __future__ import annotations

from src.models.diff import FileDiff
from src.models.conflict import ConflictAnalysis


EXECUTOR_SYSTEM = """You are a code merge executor. Your task is to apply merge decisions to files,
performing semantic merges when needed. You must be precise and preserve all important logic from both branches.
Never lose code that may be functionally important."""


def build_semantic_merge_prompt(
    file_diff: FileDiff,
    conflict_analysis: ConflictAnalysis,
    current_content: str,
    target_content: str,
    project_context: str,
) -> str:
    language = file_diff.language or "unknown"
    rec_val = (
        conflict_analysis.recommended_strategy.value
        if hasattr(conflict_analysis.recommended_strategy, "value")
        else conflict_analysis.recommended_strategy
    )

    return f"""Perform a semantic merge of the following two versions of a file.

# Project Context
{project_context or "No project context provided."}

# File: {file_diff.file_path}
Language: {language}

# Conflict Analysis
- Type: {conflict_analysis.conflict_type.value if hasattr(conflict_analysis.conflict_type, "value") else conflict_analysis.conflict_type}
- Recommended strategy: {rec_val}
- Rationale: {conflict_analysis.rationale}
- Confidence: {conflict_analysis.confidence}

# Current version (fork)
```{language}
{current_content}
```

# Target version (upstream)
```{language}
{target_content}
```

Produce a merged file that:
1. Preserves fork's private/custom logic
2. Incorporates upstream bug fixes and improvements
3. Contains NO conflict markers (<<<<<<<, =======, >>>>>>>)
4. Is syntactically valid

Return ONLY the merged file content."""


def build_deletion_analysis_prompt(
    file_path: str,
    lines_deleted: int,
    project_context: str,
) -> str:
    return f"""Analyze whether the following file deletion from upstream should be applied to the fork.

# Project Context
{project_context or "No project context provided."}

# File being deleted: {file_path}
Lines deleted: {lines_deleted}

Determine the most likely reason for deletion (e.g. refactoring cleanup, feature removal, file moved/renamed)
and assess whether it is safe to apply this deletion to the fork.

Respond in this format:
REASON: <one-line reason>
SAFE_TO_DELETE: <yes/no>
RATIONALE: <explanation in 2-3 sentences>"""


def build_rebuttal_prompt(
    issues_summary: str,
    file_paths: list[str],
    project_context: str,
) -> str:
    paths_str = ", ".join(file_paths[:10])
    return f"""You are a code merge executor reviewing a judge's assessment of your merge work.

# Project Context
{project_context or "No project context provided."}

# Files reviewed: {paths_str}

# Judge's Issues
{issues_summary}

For each issue, decide whether to:
A) ACCEPT: You agree the issue is valid and will repair it.
B) DISPUTE: You have evidence the issue is a false positive or already handled.

Respond in JSON format:
{{
  "accepts_all": true/false,
  "decisions": [
    {{"issue_id": "<id>", "action": "accept"|"dispute", "counter_evidence": "<evidence if disputing>"}}
  ],
  "overall_rationale": "<brief overall summary>"
}}"""
