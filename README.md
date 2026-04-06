# CodeMergeSystem

A multi-agent system for automating code merges between upstream and fork branches, with semantic conflict resolution, risk-based routing, and human-in-the-loop escalation.

## Overview

The system orchestrates six specialized agents in a pipeline:

| Agent | Role | LLM |
|-------|------|-----|
| **Planner** | Analyzes diffs, generates phased merge plan | Claude Opus |
| **PlannerJudge** | Independently reviews merge plan quality | GPT-4o |
| **ConflictAnalyst** | Analyzes high-risk conflict semantics | Claude Sonnet |
| **Executor** | Applies file-level merge decisions | GPT-4o |
| **Judge** | Reviews merged results for correctness | Claude Opus |
| **HumanInterface** | Generates reports, collects human decisions | Claude Haiku |

Key design principles:
- Reviewer agents (Judge, PlannerJudge) use a different LLM provider than executor agents
- Human decisions are always explicit — no timeout-based auto-defaults
- All file writes are snapshotted before execution; failures auto-rollback
- Full checkpoint/resume support at every phase boundary

## Requirements

- Python 3.11+
- `ANTHROPIC_API_KEY` — for Planner, ConflictAnalyst, Judge, HumanInterface
- `OPENAI_API_KEY` — for PlannerJudge, Executor

## Installation

```bash
# 1. Clone the repo (skip if already cloned)
git clone <repo-url> && cd CodeMergeSystem

# 2. Create a virtual environment (recommended)
python3.11 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"

# 4. Verify installation
merge --help                     # CLI should print usage
mypy src                         # type check
pytest tests/unit/ -q            # run tests
```

### Rebuild after code changes

Any changes to source files under `src/` take effect immediately because editable mode (`-e`) links directly to the source tree. You only need to re-run `pip install` when dependencies in `pyproject.toml` change:

```bash
# After modifying pyproject.toml dependencies
pip install -e ".[dev]"

# Force full rebuild (clears cached artifacts)
pip install -e ".[dev]" --no-build-isolation --force-reinstall
```

### Build a distributable wheel

```bash
pip install build                # install build tool (one-time)
python -m build                  # outputs dist/*.whl and dist/*.tar.gz

# Install the wheel on another machine
pip install dist/code_merge_system-0.1.0-py3-none-any.whl
```

## Quick Start

```bash
# 1. Copy the default config template and edit it
cp config/default.yaml config/my-merge.yaml

# 2. Edit upstream_ref / fork_ref / repo_path to match your repository
#    Set API keys in your shell:
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."

# 3. Validate config and environment
merge validate --config config/my-merge.yaml

# 4. Dry run (analysis only, no file writes)
merge run --config config/my-merge.yaml --dry-run

# 5. Run full merge
merge run --config config/my-merge.yaml
```

## Usage

```bash
# Validate config and check all required env vars
merge validate --config config/my-merge.yaml

# Full merge execution
merge run --config config/my-merge.yaml

# Dry run — only analyze, do not write files
merge run --config config/my-merge.yaml --dry-run

# CI mode — no interaction, exit codes, JSON summary to stdout
merge run --config config/my-merge.yaml --ci

# Export human decision template when the run pauses at AWAITING_HUMAN
merge run --config config/my-merge.yaml --export-decisions decisions.yaml

# Resume from checkpoint after interruption or human review
merge resume --run-id <run-id>

# Resume with human decisions file
merge resume --run-id <run-id> --decisions decisions.yaml

# Generate reports from a completed run
merge report --run-id <run-id> --output ./outputs

# Interactive setup wizard (creates config + checks keys)
merge init

# Web UI for reviewing merge decisions
merge ui --run-id <run-id> --port 8080
```

## Configuration

Copy `config/default.yaml` as your starting point, then edit the fields below:

```bash
cp config/default.yaml config/my-merge.yaml
```

The only fields you **must** change:

```yaml
upstream_ref: "upstream/main"       # the branch you want to merge FROM
fork_ref: "feature/my-fork"         # your current branch
repo_path: "."                      # path to the git repo (default: cwd)
project_context: "Describe your project so LLMs understand the codebase."
```

Key tunable parameters (with defaults):

```yaml
max_plan_revision_rounds: 2         # Planner↔Judge max negotiation rounds

thresholds:
  auto_merge_confidence: 0.85       # above this → auto merge
  human_escalation: 0.60            # below this → escalate to human
  risk_score_low: 0.30              # below → AUTO_SAFE
  risk_score_high: 0.60             # above → HUMAN_REQUIRED

output:
  directory: ./outputs              # reports and checkpoints go here
  formats: [json, markdown]
```

See `config/default.yaml` for the full configuration reference including per-agent LLM settings.

## Development

```bash
# Run unit tests
pytest tests/unit/ -v

# Run all tests with coverage
pytest --cov=src tests/

# Type check
mypy src

# Lint
ruff check src/

# Format
ruff format src/
```

## Architecture

```
src/
├── models/     # Pydantic data models (config, state, plan, decision, etc.)
├── tools/      # Git operations, diff parsing, file classification, patch application
├── llm/        # LLM client abstraction, prompt templates, response parsers
├── agents/     # Six specialized agents
├── core/       # Orchestrator, state machine, checkpointing, message bus
└── cli/        # Click CLI (run, resume, report, validate)
```

See `doc/` for detailed design documentation:
- `doc/architecture.md` — directory structure and tech stack
- `doc/agents.md` — agent responsibilities and LLM configuration
- `doc/flow.md` — state machine and 6-phase execution flow
- `doc/data-models.md` — all Pydantic model definitions
- `doc/implementation-plan.md` — algorithm design and prompt frameworks
