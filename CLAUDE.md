# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"          # install with dev deps
pytest tests/unit/               # unit tests only
pytest                           # all tests
pytest -k "test_name"            # single test
mypy src                         # type check (strict mode)
ruff check src/                  # lint
ruff format src/                 # format
merge --help                     # CLI entry point
merge validate --config <path>   # validate config + env vars
merge run --config <path>        # run full merge
merge resume --run-id <id>       # resume from checkpoint
```

## Required Environment Variables

Each agent reads its API key from its own env var — no key is hardcoded:

| Agent | Env var |
|-------|---------|
| planner, conflict_analyst, judge, human_interface | `ANTHROPIC_API_KEY` |
| planner_judge, executor | `OPENAI_API_KEY` |

Run `merge validate --config <path>` to check all vars before running.

## Architecture Constraints

These are load-bearing design rules enforced by unit tests — do not violate them:

- **No `TIMEOUT_DEFAULT`** — `DecisionSource` enum has no timeout-based value; human decisions must be explicit
- **No `human_decision_timeout_hours`** — `MergeConfig` has no such field
- **Judge / PlannerJudge are read-only** — their `run()` receives `ReadOnlyStateView`; all writes go through Orchestrator
- **Executor must snapshot before writing** — use `apply_with_snapshot()` in `patch_applier.py`; never write files directly
- **Plan dispute does not modify `risk_level`** — `raise_plan_dispute()` only appends to `state.plan_disputes`
- **HumanInterface never fills defaults** — skipped items keep `ESCALATE_HUMAN` status until the user explicitly decides
- **Plan revision limit** — when `plan_revision_rounds >= max_plan_revision_rounds`, transition to `AWAITING_HUMAN`, not `FAILED`
- **Plan human review is mandatory** — after PlannerJudge approves the plan, the system transitions to `AWAITING_HUMAN` (not directly to `AUTO_MERGING`). The human must set `state.plan_human_review` with a `PlanHumanDecision` (approve/reject/modify) before the system proceeds. A `plan_review_<run_id>.md` report is generated in `output.directory`, documenting all planner-judge interaction rounds and the human review record.

## Configuration

Config is YAML-driven. Each agent has its own `AgentLLMConfig` (provider, model, `api_key_env`). The `agents` block in `MergeConfig` is the authoritative per-agent config; the top-level `llm` block is a legacy global default.

Key config thresholds: `risk_score_low=0.3`, `risk_score_high=0.6`, `auto_merge_confidence=0.85`. Files matching `security_sensitive.patterns` are forced to `HUMAN_REQUIRED`.

## Code Style

- Python 3.11+, `async`/`await` throughout
- Pydantic v2 syntax (`model_dump()`, `Field(default_factory=...)`, `@field_validator`)
- Immutable patterns — return new objects, never mutate in place
- Files stay under 800 lines; organize by feature layer (models → tools → llm → agents → core → cli)
- mypy strict mode is enforced — all new code must pass `mypy src`
