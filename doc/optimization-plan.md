# Optimization Plan: Lessons from Production Merge Practice

> Based on analysis of real-world upstream merge execution on the Dify project (1.13.0 merge, 10,793 files, 14 Phases, 4 rounds of Judge review per Phase).
>
> Source materials:
> - `UPSTREAM_MERGE_SPECIFICATION.md` — merge execution specification
> - `merge-executor` skill — Executor orchestration logic
> - `merge-judging` skill — Judge review protocol
> - `MERGE_PLAN_1.13.0.md` — production merge plan with execution records

---

## Table of Contents

1. [Gap Analysis Summary](#1-gap-analysis-summary)
2. [P0: Three-Way Classification Model (ABCDE)](#2-p0-three-way-classification-model-abcde)
3. [P0: Layered Merge Ordering](#3-p0-layered-merge-ordering)
4. [P1: Customization Protection Registry](#4-p1-customization-protection-registry)
5. [P1: Judge-Executor Repair Loop](#5-p1-judge-executor-repair-loop)
6. [P1: Gate System](#6-p1-gate-system)
7. [P2: Living Merge Plan Document](#7-p2-living-merge-plan-document)
8. [P2: Three-Way Diff in Judge](#8-p2-three-way-diff-in-judge)
9. [P3: Configuration Drift Detection](#9-p3-configuration-drift-detection)
10. [P3: Pollution Audit / Pre-Check](#10-p3-pollution-audit--pre-check)
11. [Implementation Roadmap](#11-implementation-roadmap)

---

## 1. Gap Analysis Summary

| Dimension | Production Practice | Current System | Gap Severity |
|-----------|-------------------|----------------|--------------|
| File classification | ABCDE three-way (base/HEAD/upstream) | Risk-score only (AUTO_SAFE/RISKY/HUMAN) | **Critical** |
| Merge ordering | Layer 0-9 dependency-aware | Flat functional phases (ANALYSIS→MERGE→REVIEW) | **Critical** |
| Customization protection | Explicit registry + Judge grep verification | SecuritySensitiveConfig patterns only | **High** |
| Judge-Executor loop | Multi-round repair (up to 4 rounds observed) | Judge → Human only, no Executor repair path | **High** |
| Gate system | Per-phase lint/typecheck/test/build with baseline | syntax_checker.py basic check only | **High** |
| Merge plan tracking | Living document with execution/review/gate records | In-memory Pydantic model, phases + risk_summary only | **Medium** |
| Three-way diff in Judge | `diff3` base/upstream/merged + VETO rules | LLM review of high-risk records only | **Medium** |
| Config drift detection | Code default vs .env vs docker .env consistency check | Not implemented | **Low** |
| Pollution audit | Phase -1 pre-merge audit of prior incomplete merges | Assumes clean starting state | **Low** |

---

## 2. P0: Three-Way Classification Model (ABCDE)

### Problem

The current system classifies files solely by risk score (`compute_risk_score` in `file_classifier.py`), which conflates **change ownership** with **merge difficulty**. A B-class file (only upstream changed) should always be directly adopted regardless of its risk score, but the current system may flag it as `HUMAN_REQUIRED` if it touches auth code.

### Design

#### New Enum: `FileChangeCategory`

```python
# src/models/diff.py

class FileChangeCategory(str, Enum):
    A = "unchanged"           # HEAD == upstream, skip
    B = "upstream_only"       # HEAD == base, adopt upstream
    C = "both_changed"        # HEAD != base AND upstream != base, three-way merge
    D_MISSING = "upstream_new"  # file exists in upstream only
    D_EXTRA = "current_only"  # file exists in HEAD only
    E = "current_only_change" # upstream == base, keep current
```

#### Classification Logic

```python
# src/tools/file_classifier.py

def classify_three_way(
    file_path: str,
    merge_base: str,
    head_ref: str,
    upstream_ref: str,
    git_tool: GitTool,
) -> FileChangeCategory:
    base_hash = git_tool.get_file_hash(merge_base, file_path)
    head_hash = git_tool.get_file_hash(head_ref, file_path)
    up_hash = git_tool.get_file_hash(upstream_ref, file_path)

    if head_hash is None and up_hash is not None:
        return FileChangeCategory.D_MISSING
    if head_hash is not None and up_hash is None:
        return FileChangeCategory.D_EXTRA
    if head_hash == up_hash:
        return FileChangeCategory.A
    if head_hash == base_hash:
        return FileChangeCategory.B
    if up_hash == base_hash:
        return FileChangeCategory.E
    return FileChangeCategory.C
```

#### Impact on Merge Strategy

| Category | Strategy | Agent Involvement |
|----------|----------|-------------------|
| A | Skip | None |
| B | `git show upstream:path > path` | Executor only, no LLM |
| C | Three-way merge (LLM-assisted for complex) | Executor + ConflictAnalyst + Judge |
| D_MISSING | Copy from upstream | Executor only |
| D_EXTRA | Keep current | None |
| E | Keep current | None |

#### Files to Modify

- `src/models/diff.py` — add `FileChangeCategory` enum, add `change_category` field to `FileDiff`
- `src/tools/file_classifier.py` — add `classify_three_way()`, refactor `classify_file()` to use category as primary input
- `src/tools/git_tool.py` — add `get_file_hash(ref, path)` method
- `src/agents/planner_agent.py` — generate plan based on ABCDE categories, not just risk scores
- `src/agents/executor_agent.py` — dispatch merge strategy by category
- `src/models/state.py` — add `file_categories: dict[str, FileChangeCategory]`

---

## 3. P0: Layered Merge Ordering

### Problem

The current `MergePhase` enum represents functional stages (ANALYSIS, AUTO_MERGE, etc.), not dependency-aware merge layers. In practice, merging `api/services/` before `api/models/` causes import errors and test failures that block progress.

### Design

#### New Model: `MergeLayer`

```python
# src/models/plan.py

class MergeLayer(BaseModel):
    layer_id: int
    name: str
    description: str
    path_patterns: list[str]
    depends_on: list[int] = Field(default_factory=list)
    gate_commands: list[str] = Field(default_factory=list)
```

#### Default Layer Configuration

```yaml
# config/default-layers.yaml
layers:
  - id: 0
    name: "infrastructure"
    patterns: ["docker/**", "dev/**", "ci/**", ".github/**", "Makefile", ".gitignore"]
    gate: ["docker compose config -q"]

  - id: 1
    name: "dependencies"
    patterns: ["**/pyproject.toml", "**/package.json", "**/uv.lock", "**/pnpm-lock.yaml"]
    depends_on: [0]
    gate: ["cd api && uv sync", "cd web && pnpm install"]

  - id: 2
    name: "types_configs"
    patterns: ["**/types/**", "**/configs/**", "**/constants/**", "**/enums/**"]
    depends_on: [1]
    gate: ["cd api && ruff check .", "cd web && pnpm type-check"]

  - id: 3
    name: "models_extensions"
    patterns: ["**/models/**", "**/extensions/**", "**/libs/**", "**/migrations/**"]
    depends_on: [2]
    gate: ["cd api && ruff check .", "cd api && pytest tests/unit_tests/ -x -q"]

  - id: 4
    name: "core_engine"
    patterns: ["**/core/**"]
    depends_on: [3]
    gate: ["cd api && pytest tests/unit_tests/core/ -x -q"]

  - id: 5
    name: "services_controllers"
    patterns: ["**/services/**", "**/tasks/**", "**/controllers/**"]
    depends_on: [4]
    gate: ["cd api && pytest tests/unit_tests/ -x -q"]

  - id: 6
    name: "frontend"
    patterns: ["web/app/**", "web/service/**"]
    depends_on: [2]
    gate: ["cd web && pnpm type-check", "cd web && pnpm build:fast"]

  - id: 7
    name: "i18n"
    patterns: ["**/i18n/**"]
    depends_on: [6]

  - id: 8
    name: "tests"
    patterns: ["**/tests/**", "**/__tests__/**", "**/e2e/**"]
    depends_on: [4, 5, 6]

  - id: 9
    name: "sdk_plugins"
    patterns: ["sdks/**", "plugins/**"]
    depends_on: [5]
```

#### Planner Enhancement

The Planner should:

1. Classify all files into ABCDE categories
2. Assign each file to a layer based on path patterns
3. Within each layer, further group by sub-module for manageable batch sizes
4. Generate `PhaseFileBatch` entries ordered by layer dependency

#### Files to Modify

- `src/models/plan.py` — add `MergeLayer`, add `layer_id` to `PhaseFileBatch`
- `src/models/config.py` — add `layers: list[MergeLayer]` to `MergeConfig` with default factory
- `src/agents/planner_agent.py` — layer-aware plan generation
- `src/core/orchestrator.py` — enforce layer ordering, run gates between layers

---

## 4. P1: Customization Protection Registry

### Problem

Fork branches accumulate critical customizations (SSO, custom auth, proprietary extensions). The current system has no way to declare these, track them, or verify they survive merging. In the Dify merge, the "customization protection checklist" was the #1 defense against regression.

### Design

#### New Config Section

```yaml
# In merge config YAML
customizations:
  - name: "HTTP-only Cookie Auth"
    description: "Replace localStorage token with HTTP-only cookies + CSRF"
    files:
      - "api/controllers/console/auth/login.py"
      - "web/service/base.ts"
    verification:
      - type: "grep"
        pattern: "set_cookie|csrf_token|passport"
        files: ["api/controllers/console/auth/**"]
      - type: "grep"
        pattern: "credentials.*include"
        files: ["web/service/base.ts"]

  - name: "SSO Integration"
    description: "CVTE Portal SSO / KeyCloak SSO"
    files:
      - "api/controllers/console/auth/oauth_server.py"
    verification:
      - type: "grep"
        pattern: "portal_sso|keycloak"
        files: ["api/controllers/console/auth/**"]

  - name: "ext_socketio"
    description: "Flask-SocketIO extension for realtime"
    files:
      - "api/app_factory.py"
      - "api/extensions/ext_socketio.py"
    verification:
      - type: "grep"
        pattern: "init_app.*socketio"
        files: ["api/app_factory.py"]
```

#### New Model

```python
# src/models/config.py

class CustomizationVerification(BaseModel):
    type: Literal["grep", "file_exists", "function_exists"]
    pattern: str = ""
    files: list[str] = Field(default_factory=list)

class CustomizationEntry(BaseModel):
    name: str
    description: str
    files: list[str]
    verification: list[CustomizationVerification] = Field(default_factory=list)
```

#### Judge Integration

After each Phase, the Judge runs all customization verifications and produces a **Customization Survival Report**:

```
Customization Survival Report — Phase 5
| Customization | Status | Details |
|--------------|--------|---------|
| HTTP-only Cookie Auth | PASS | grep found 3 matches in auth/ |
| SSO Integration | PASS | grep found 2 matches |
| ext_socketio | FAIL | grep 0 matches in app_factory.py |
```

Any `FAIL` triggers a VETO (hard rejection).

#### Files to Modify

- `src/models/config.py` — add `CustomizationEntry`, `CustomizationVerification`, add `customizations` field to `MergeConfig`
- `src/agents/judge_agent.py` — add `verify_customizations()` method, integrate into review flow
- `src/tools/git_tool.py` — add `grep_in_file(pattern, path)` utility

---

## 5. P1: Judge-Executor Repair Loop

### Problem

Currently, when the Judge finds issues, the only path is `JUDGE_REVIEWING → AWAITING_HUMAN`. In practice, most Judge findings are mechanical (missing function, incomplete merge) and can be directly repaired by the Executor without human intervention. The Dify merge showed Phases going through 3-4 rounds of Judge → Executor repair.

### Design

#### New State Transitions

```
JUDGE_REVIEWING
  ├─[PASS]─────────────────→ GENERATING_REPORT (or next layer)
  ├─[CONDITIONAL]──────────→ AUTO_MERGING (Executor repairs, then re-review)
  ├─[FAIL + repairable]───→ AUTO_MERGING (Executor repairs, then re-review)
  ├─[FAIL + VETO]──────────→ AWAITING_HUMAN
  └─[max_repair_rounds]───→ AWAITING_HUMAN
```

#### Judge Output Enhancement

```python
# src/models/judge.py

class JudgeVerdict(BaseModel):
    verdict: VerdictType  # PASS, CONDITIONAL, FAIL
    issues: list[JudgeIssue]
    veto_triggered: bool = False
    repair_instructions: list[RepairInstruction] = Field(default_factory=list)
    # New: structured repair instructions for Executor

class RepairInstruction(BaseModel):
    file_path: str
    instruction: str
    severity: IssueSeverity
    is_repairable: bool = True  # False = must escalate to human
```

#### Orchestrator Loop

```python
# Pseudocode for the repair loop in orchestrator.py

MAX_REPAIR_ROUNDS = 3

for round_num in range(MAX_REPAIR_ROUNDS):
    verdict = await judge.run(read_only_view)

    if verdict.verdict == VerdictType.APPROVED:
        break

    if verdict.veto_triggered:
        transition_to(AWAITING_HUMAN)
        break

    repairable = [r for r in verdict.repair_instructions if r.is_repairable]
    if not repairable:
        transition_to(AWAITING_HUMAN)
        break

    # Executor repairs
    await executor.repair(repairable)
    # Loop continues → Judge re-reviews

if round_num == MAX_REPAIR_ROUNDS - 1:
    transition_to(AWAITING_HUMAN)
```

#### Files to Modify

- `src/models/judge.py` — add `RepairInstruction`, add `repair_instructions` and `veto_triggered` to `JudgeVerdict`
- `src/core/state_machine.py` — add `JUDGE_REVIEWING → AUTO_MERGING` transition
- `src/core/orchestrator.py` — implement repair loop with round tracking
- `src/agents/executor_agent.py` — add `repair(instructions)` method
- `src/agents/judge_agent.py` — generate structured `RepairInstruction` in verdict
- `src/models/state.py` — add `judge_repair_rounds: int = 0`

---

## 6. P1: Gate System

### Problem

The current system only has `syntax_checker.py` for basic syntax validation. Production merges require per-layer gate checks (lint, type-check, test, build) with baseline comparison. Gate failures must block the current phase and trigger rollback after 3 consecutive failures.

### Design

#### New Model

```python
# src/models/config.py

class GateCommand(BaseModel):
    name: str
    command: str
    working_dir: str = "."
    timeout_seconds: int = 300
    pass_criteria: Literal["exit_zero", "not_worse_than_baseline"] = "exit_zero"

class GateBaseline(BaseModel):
    gate_name: str
    baseline_value: str  # e.g., "5616 passed, 6 failed"
    recorded_at: datetime
```

#### Gate Runner

```python
# src/tools/gate_runner.py

class GateRunner:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    async def run_gate(self, gate: GateCommand) -> GateResult:
        """Execute a gate command and return structured result."""

    async def run_all_gates(
        self, gates: list[GateCommand], baseline: dict[str, GateBaseline] | None
    ) -> GateReport:
        """Run all gates for a layer, compare against baseline."""

    def record_baseline(self, gates: list[GateCommand]) -> dict[str, GateBaseline]:
        """Record initial baseline for all gates (Phase 0)."""

class GateResult(BaseModel):
    gate_name: str
    passed: bool
    exit_code: int
    stdout_tail: str  # last 20 lines
    duration_seconds: float

class GateReport(BaseModel):
    all_passed: bool
    results: list[GateResult]
    baseline_comparison: dict[str, str]  # gate_name -> "improved" | "same" | "regressed"
```

#### Orchestrator Integration

After each layer completes:

1. Run all gate commands for that layer
2. Compare against baseline (recorded in Phase 0)
3. If any gate fails:
   - Increment `consecutive_gate_failures`
   - If < 3: log warning, allow Executor to fix
   - If >= 3: rollback to last passing commit, reduce merge batch size

#### Files to Create

- `src/tools/gate_runner.py` — gate execution engine

#### Files to Modify

- `src/models/config.py` — add `GateCommand`, `GateBaseline`
- `src/models/state.py` — add `gate_baselines`, `gate_history`, `consecutive_gate_failures`
- `src/core/orchestrator.py` — integrate gate checks after each layer

---

## 7. P2: Living Merge Plan Document

### Problem

The current `MergePlan` model (`src/models/plan.py`) only captures the initial plan (phases, risk summary). In practice, the merge plan is a living document that accumulates execution records, Judge review records, gate results, and open issues throughout the merge.

### Design

#### Enhanced MergePlan

```python
# src/models/plan.py

class PhaseExecutionRecord(BaseModel):
    phase_id: str
    started_at: datetime
    completed_at: datetime | None = None
    files_processed: int = 0
    files_skipped: int = 0
    commit_hash: str | None = None
    notes: list[str] = Field(default_factory=list)

class PhaseJudgeRecord(BaseModel):
    phase_id: str
    round_number: int
    verdict: str  # PASS / CONDITIONAL / FAIL
    reviewed_at: datetime
    issues: list[dict[str, str]] = Field(default_factory=list)
    veto_triggered: bool = False
    repair_instructions: list[str] = Field(default_factory=list)

class PhaseGateRecord(BaseModel):
    phase_id: str
    gate_results: list[GateResult]
    all_passed: bool

class OpenIssue(BaseModel):
    issue_id: str
    phase_id: str
    description: str
    severity: str
    assigned_to_phase: str | None = None  # deferred to which phase
    resolved: bool = False

class MergePlanLive(MergePlan):
    """Extended MergePlan with runtime tracking."""
    execution_records: list[PhaseExecutionRecord] = Field(default_factory=list)
    judge_records: list[PhaseJudgeRecord] = Field(default_factory=list)
    gate_records: list[PhaseGateRecord] = Field(default_factory=list)
    open_issues: list[OpenIssue] = Field(default_factory=list)
    todo_merge_count: int = 0
    todo_merge_limit: int = 30
```

#### Markdown Export

The `report_writer.py` should be able to export this living plan to a Markdown file (similar to `MERGE_PLAN_1.13.0.md`) that serves as the single source of truth.

#### Files to Modify

- `src/models/plan.py` — add execution/judge/gate record models, extend `MergePlan`
- `src/tools/report_writer.py` — add `write_living_plan_report()`
- `src/core/orchestrator.py` — append records after each phase/review/gate

---

## 8. P2: Three-Way Diff in Judge

### Problem

The current Judge only does LLM-based review of high-risk records. The production Judge skill performs deterministic three-way comparison (base vs upstream vs merged) and has 6 hard VETO rules that catch mechanical errors without LLM involvement.

### Design

#### VETO Rules

```python
# src/agents/judge_agent.py

VETO_CONDITIONS = [
    "B-class file differs from upstream (diff non-empty)",
    "D-missing file not present in HEAD",
    "Customization item disappeared without TODO [merge] annotation",
    "Upstream function block (>20 lines) completely missing in merged",
    "TODO [merge] count exceeds phase limit (30/phase)",
    "Unannotated TODO [check] exists (prohibited)",
]
```

#### Deterministic Review Pipeline

Before LLM review, the Judge runs:

1. **B-class verification**: For each B-class file, `diff upstream_version merged_version` must be empty
2. **D-missing verification**: Each D-missing file must exist in HEAD
3. **Upstream completeness**: For each C-class file, extract upstream-added functions/methods and verify they exist in merged
4. **Customization survival**: Run all customization verifications (see section 4)
5. **TODO audit**: Count `TODO [merge]` markers, check for prohibited `TODO [check]`

Only files that pass all deterministic checks proceed to LLM review.

#### New Tool

```python
# src/tools/three_way_diff.py

class ThreeWayDiff:
    def __init__(self, git_tool: GitTool):
        self.git_tool = git_tool

    def compare(
        self, file_path: str, merge_base: str, upstream_ref: str
    ) -> ThreeWayResult:
        """Get base, upstream, and current content for comparison."""

    def verify_b_class(self, file_path: str, upstream_ref: str) -> bool:
        """B-class file must exactly match upstream."""

    def extract_upstream_additions(
        self, file_path: str, merge_base: str, upstream_ref: str
    ) -> list[str]:
        """Extract function/class names added by upstream."""

    def verify_additions_present(
        self, file_path: str, additions: list[str]
    ) -> list[str]:
        """Return list of upstream additions missing from merged file."""
```

#### Files to Create

- `src/tools/three_way_diff.py` — three-way comparison utilities

#### Files to Modify

- `src/agents/judge_agent.py` — add deterministic review pipeline before LLM review
- `src/models/judge.py` — add `veto_condition` field to `JudgeIssue`

---

## 9. P3: Configuration Drift Detection

### Problem

When merging configuration files (`.env.example`, docker env, Pydantic Settings), code defaults, env file defaults, and docker env defaults can diverge silently. The Dify merge discovered `WORKFLOW_LOG_CLEANUP_ENABLED` had code default `True` but env default `false` — opposite behaviors depending on deployment method.

### Design

#### New Tool

```python
# src/tools/config_drift_detector.py

class ConfigDriftDetector:
    def detect_drift(
        self,
        code_defaults: dict[str, str],
        env_defaults: dict[str, str],
        docker_env_defaults: dict[str, str],
    ) -> list[ConfigDrift]:
        """Compare three sources of config defaults."""

class ConfigDrift(BaseModel):
    key: str
    code_default: str | None
    env_default: str | None
    docker_default: str | None
    impact: str
    suggestion: str
```

This tool would be invoked by the Planner during Layer 1 (dependencies) analysis and its findings included in the merge plan.

#### Files to Create

- `src/tools/config_drift_detector.py`

#### Files to Modify

- `src/agents/planner_agent.py` — invoke drift detection during plan generation

---

## 10. P3: Pollution Audit / Pre-Check

### Problem

Real-world branches may have been partially merged before. The Dify merge discovered 407 files from a prior incomplete merge (`f980df6acf`) that polluted the ABCDE classification. Without a Phase -1 audit, the entire classification matrix is unreliable.

### Design

#### Pre-Merge Audit

Before generating the merge plan, the system should:

1. Check for prior merge commits from upstream: `git log --grep="merge.*upstream" --oneline`
2. For each such commit, identify files it introduced
3. Cross-reference with current ABCDE classification
4. Flag files whose classification may be inaccurate
5. Generate a `pollution_audit_report` with:
   - Files that were A-class but may have lost customizations (A-overwritten)
   - Files that were E-class but are actually upstream residue (E-residue)
   - Files that were B-class but already contain partial upstream code
6. Reclassify affected files and produce a corrected classification matrix

#### Integration Point

This runs as part of `Phase 0 / INITIALIZED → PLANNING` transition, before the Planner generates the plan.

#### Files to Create

- `src/tools/pollution_auditor.py`

#### Files to Modify

- `src/core/orchestrator.py` — invoke pollution audit before planning
- `src/models/state.py` — add `pollution_audit: PollutionAuditReport | None`

---

## 11. Implementation Roadmap

### Phase 1: Foundation (P0 items)

**Goal**: Replace risk-score-only classification with ABCDE + layer-aware ordering.

| Step | Task | Effort |
|------|------|--------|
| 1.1 | Add `FileChangeCategory` enum and `classify_three_way()` | S |
| 1.2 | Add `get_file_hash(ref, path)` to `GitTool` | S |
| 1.3 | Add `MergeLayer` model and default layer config | M |
| 1.4 | Refactor `PlannerAgent` to generate layer-ordered ABCDE plans | L |
| 1.5 | Refactor `ExecutorAgent` to dispatch by category (B→adopt, C→merge, D→copy) | M |
| 1.6 | Update `MergeState` with new fields | S |
| 1.7 | Update existing tests, add classification tests | M |

**Validation**: Generate plan for a test repo and verify correct ABCDE classification + layer ordering.

### Phase 2: Quality Assurance (P1 items)

**Goal**: Add customization protection, Judge-Executor repair loop, and gate system.

| Step | Task | Effort |
|------|------|--------|
| 2.1 | Add `CustomizationEntry` config and verification logic | M |
| 2.2 | Add `RepairInstruction` to Judge output | S |
| 2.3 | Implement repair loop in Orchestrator (max 3 rounds) | M |
| 2.4 | Add `repair()` method to `ExecutorAgent` | M |
| 2.5 | Create `gate_runner.py` with baseline recording | M |
| 2.6 | Integrate gates into Orchestrator layer transitions | M |
| 2.7 | Update state machine transitions | S |
| 2.8 | Tests for repair loop, gates, customization verification | L |

**Validation**: End-to-end test with deliberate Judge failures triggering Executor repair.

### Phase 3: Observability (P2 items)

**Goal**: Living merge plan + deterministic three-way Judge review.

| Step | Task | Effort |
|------|------|--------|
| 3.1 | Extend `MergePlan` with execution/judge/gate records | M |
| 3.2 | Add Markdown export for living plan | M |
| 3.3 | Create `three_way_diff.py` tool | M |
| 3.4 | Implement VETO rules in Judge (deterministic layer) | M |
| 3.5 | Add upstream completeness verification | M |
| 3.6 | Tests for three-way diff and VETO rules | M |

**Validation**: Judge correctly VETOs when B-class file doesn't match upstream.

### Phase 4: Robustness (P3 items)

**Goal**: Config drift detection and pollution audit.

| Step | Task | Effort |
|------|------|--------|
| 4.1 | Create `config_drift_detector.py` | S |
| 4.2 | Create `pollution_auditor.py` | M |
| 4.3 | Integrate both into planning phase | S |
| 4.4 | Tests | M |

**Validation**: Detect known drift cases and reclassify polluted files.

---

## Size Legend

- **S** (Small): < 100 lines, < 2 hours
- **M** (Medium): 100-300 lines, 2-6 hours
- **L** (Large): 300+ lines, 6+ hours
