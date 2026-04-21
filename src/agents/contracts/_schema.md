# Agent Contracts

Each `<name>.yaml` in this directory is the **single source of truth** for one
agent's behavioral contract.  The schema is defined and validated by
[`src/agents/contract.py`](../contract.py) (`AgentContract` Pydantic model).

## Fields

| Field | Type | Purpose |
|---|---|---|
| `name` | str | Must equal the file stem and the `AgentRegistry` key. |
| `inputs` | list[str] | Whitelist of `MergeState` attributes the agent may read. Access to fields outside this list raises `FieldNotInContract` when the agent runs against a restricted `ReadOnlyStateView`. |
| `output_schema` | str | Name of the Pydantic model the agent's `run()` returns (or wraps in an `AgentMessage.payload`). |
| `gates` | list[str] | Prompt gate IDs (registered in `src/llm/prompts/gate_registry.py`) that this agent is permitted to invoke. |
| `forbidden` | list[ForbiddenRule] | Behaviors the agent must never exhibit. Enforced by `tests/unit/test_agent_contracts.py` via AST/text scan plus runtime assertions where practical. |
| `collaboration` | enum | `compute` / `review_only` / `propose_then_confirm`. Controls how the orchestrator and HumanInterface interpret outputs. |
| `requires_human_options` | bool | When true, any user-facing decision must render ≥2 labeled options with a recommended pick (CCGS "Ask→Options→Decide" pattern). |

## Forbidden rules

| Rule | Meaning | How it is enforced |
|---|---|---|
| `writes_state` | Agent must not mutate `MergeState` directly. | Static scan: no left-hand assignment `state\.\w+\s*=` in the agent module. Runtime: `ReadOnlyStateView` raises `PermissionError` on `__setattr__`. |
| `direct_llm_call` | Agent must not bypass `BaseAgent._call_llm_with_retry`. | Static scan: `self.llm.complete(` / `self.llm.chat(` not allowed outside `base_agent.py`. |
| `fills_missing_fields_with_defaults` | Agent must not silently substitute defaults for absent LLM output fields. | Static scan: no `... or <literal>` / `.get(..., <literal>)` over known required fields. (Partial — relies on reviewer discipline.) |

## Collaboration patterns

- **`compute`** — pure function.  Orchestrator passes inputs, agent returns
  output.  No user interaction.  Examples: `planner`, `conflict_analyst`,
  `executor`.
- **`review_only`** — agent receives a `ReadOnlyStateView` and returns a
  verdict.  Must never write.  Examples: `judge`, `planner_judge`.
- **`propose_then_confirm`** — before any final commit, the agent presents ≥2
  options with a recommendation and waits for explicit user approval.  Used by
  `human_interface`.

## Runtime loading

Agents opt in by setting a class attribute:

```python
class PlannerJudgeAgent(BaseAgent):
    contract_name = "planner_judge"
```

`BaseAgent.contract` is a lazily-loaded property.  Agents that do not declare
`contract_name` behave exactly as before (backward compatible).

## Adding a new contract

1. Create `<name>.yaml` in this directory.
2. Declare the minimum `inputs` set — under-declaring is safer than
   over-declaring; tests will fail loudly when the agent reaches for a missing
   field.
3. Register any new prompt IDs in `src/llm/prompts/gate_registry.py`.
4. Set `contract_name` on the agent class.
5. Add coverage in `tests/unit/test_agent_contracts.py` if the agent has
   contract-specific invariants beyond the generic checks.
