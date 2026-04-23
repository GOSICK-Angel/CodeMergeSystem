---
name: add-agent
description: Step-by-step guide for adding a new agent to CodeMergeSystem. Covers contract yaml, gate registry, BaseAgent subclass, and unit tests — enforcing all existing anti-patterns.
---

Guide the user through adding a new agent to CodeMergeSystem using this checklist:

## Step 1 — Contract YAML

Create `src/agents/contracts/<name>.yaml`. Read `src/agents/contracts/_schema.md` for the full schema. Key fields:
- `contract_name`: matches the class attribute
- `inputs`: whitelist of `MergeState` fields this agent may read
- `output_schema`: shape of the dict returned by `run()`
- `allowed_gate_ids`: list of `P-*`/`J-*`/etc. IDs from `gate_registry.py`
- `forbidden_behaviors`: document what the agent must NOT do (e.g., state writes for reviewers)
- `collaboration_pattern`: e.g., `read_only_reviewer` or `stateful_writer`

## Step 2 — Gate Registry

If the agent needs a new prompt, register it in `src/llm/prompts/gate_registry.py` with a stable ID. Reference only by ID (`get_gate("<ID>")`) — never import the prompt builder directly in the agent.

## Step 3 — BaseAgent Subclass

Create `src/agents/<name>.py`:

```python
from src.agents.base import BaseAgent
from src.core.state import ReadOnlyStateView  # required for reviewer agents

class MyAgent(BaseAgent):
    contract_name = "<name>"

    async def run(self, state: MergeState) -> dict:
        view = self.restricted_view(state)  # enforces contract inputs
        prompt = get_gate("<ID>")
        result = await self._call_llm_with_retry(prompt, ...)  # never call self.llm directly
        if not result.get("required_field"):
            raise ModelOutputError("required_field missing")  # never fill defaults silently
        return result
```

**Anti-patterns to avoid (enforced by `tests/unit/test_agent_contracts.py`)**:
- Reviewer agents (`judge`, `planner_judge`, `human_interface`) must use `ReadOnlyStateView` — no `state.<field> = ...`
- Never bypass `_call_llm_with_retry` with direct `self.llm.*` calls
- Never substitute defaults for missing LLM output fields — raise `ModelOutputError`
- Never import a prompt builder directly — always use `get_gate("<ID>")`
- Never access a `MergeState` field not declared in the contract `inputs`

## Step 4 — Register with Orchestrator

Add the agent to the appropriate phase in `src/core/orchestrator.py` and wire up the `AgentLLMConfig` entry in the `MergeConfig` `agents` block.

## Step 5 — Unit Tests

Create `tests/unit/test_<name>.py`:
- Test normal output path
- Test `ModelOutputError` is raised (not swallowed) on incomplete LLM output
- Test `FieldNotInContract` is raised for out-of-contract state reads
- Test that `_call_llm_with_retry` is called (not the LLM directly)
- Run `pytest tests/unit/test_<name>.py -v` to verify

## Step 6 — Validate

```bash
python -m pytest tests/unit/test_agent_contracts.py -v  # contract compliance
mypy src                                                 # type check
ruff check src/                                          # lint
```

After explaining the steps, ask the user for the agent name and role so you can scaffold the specific files.
