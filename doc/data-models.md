# 数据模型文档

## 目录

- [数据模型文档](#数据模型文档)
  - [目录](#目录)
  - [1. MergeConfig — 系统输入配置](#1-mergeconfig--系统输入配置)
    - [Python (Pydantic v2)](#python-pydantic-v2)
    - [TypeScript](#typescript)
  - [2. FileDiff — 文件差异分类](#2-filediff--文件差异分类)
    - [Python (Pydantic v2)](#python-pydantic-v2-1)
    - [TypeScript](#typescript-1)
  - [3. ConflictPoint — 冲突点分析结果](#3-conflictpoint--冲突点分析结果)
    - [Python (Pydantic v2)](#python-pydantic-v2-2)
    - [TypeScript](#typescript-2)
  - [4. MergeDecision — 合并决策枚举](#4-mergedecision--合并决策枚举)
    - [Python](#python)
    - [TypeScript](#typescript-3)
  - [5. FileDecisionRecord — 文件完整决策记录](#5-filedecisionrecord--文件完整决策记录)
    - [Python (Pydantic v2)](#python-pydantic-v2-3)
    - [TypeScript](#typescript-4)
  - [6. MergePlan — 阶段化合并计划](#6-mergeplan--阶段化合并计划)
    - [Python (Pydantic v2)](#python-pydantic-v2-4)
    - [TypeScript](#typescript-5)
  - [7. JudgeVerdict — 审查结论](#7-judgeverdict--审查结论)
    - [Python (Pydantic v2)](#python-pydantic-v2-5)
    - [TypeScript](#typescript-6)
  - [8. HumanDecisionRequest — 人类裁决请求](#8-humandecisionrequest--人类裁决请求)
    - [Python (Pydantic v2)](#python-pydantic-v2-6)
    - [TypeScript](#typescript-7)
  - [9. MergeState — 全局状态机状态](#9-mergestate--全局状态机状态)
    - [Python (Pydantic v2)](#python-pydantic-v2-7)
    - [TypeScript](#typescript-8)
  - [10. PlanJudgeVerdict — 计划审查结论](#10-planjudgeverdict--计划审查结论)
    - [Python (Pydantic v2)](#python-pydantic-v2-8)
    - [TypeScript](#typescript-9)
  - [11. PlanDisputeRequest — Executor 计划质疑](#11-plandisputerequest--executor-计划质疑)
    - [Python (Pydantic v2)](#python-pydantic-v2-9)
    - [TypeScript](#typescript-10)
  - [12. AgentMessage — Agent 间消息](#12-agentmessage--agent-间消息)
    - [Python (Pydantic v2)](#python-pydantic-v2-10)
    - [TypeScript](#typescript-11)

---

## 1. MergeConfig — 系统输入配置

系统的唯一外部输入，通过 YAML 文件提供，在启动时被解析并验证。

### Python (Pydantic v2)

```python
from pydantic import BaseModel, Field, field_validator
from typing import Literal

class AgentLLMConfig(BaseModel):
    """单个 Agent 的 LLM 配置，允许每个 Agent 使用不同提供商和模型"""
    provider: Literal["anthropic", "openai"] = "anthropic"
    model: str = "claude-opus-4-6"
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(default=8192, ge=512, le=200000)
    max_retries: int = Field(default=3, ge=1)
    api_key_env: str = "ANTHROPIC_API_KEY"   # 环境变量名，不硬编码密钥

class AgentsLLMConfig(BaseModel):
    """各 Agent 独立 LLM 配置，审查者与执行者建议使用不同提供商"""
    planner: AgentLLMConfig = Field(
        default_factory=lambda: AgentLLMConfig(provider="anthropic", model="claude-opus-4-6", api_key_env="ANTHROPIC_API_KEY")
    )
    planner_judge: AgentLLMConfig = Field(
        default_factory=lambda: AgentLLMConfig(provider="openai", model="gpt-4o", api_key_env="OPENAI_API_KEY")
    )
    conflict_analyst: AgentLLMConfig = Field(
        default_factory=lambda: AgentLLMConfig(provider="anthropic", model="claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    )
    executor: AgentLLMConfig = Field(
        default_factory=lambda: AgentLLMConfig(provider="openai", model="gpt-4o", temperature=0.1, api_key_env="OPENAI_API_KEY")
    )
    judge: AgentLLMConfig = Field(
        default_factory=lambda: AgentLLMConfig(provider="anthropic", model="claude-opus-4-6", temperature=0.1, api_key_env="ANTHROPIC_API_KEY")
    )
    human_interface: AgentLLMConfig = Field(
        default_factory=lambda: AgentLLMConfig(provider="anthropic", model="claude-haiku-4-5-20251001", api_key_env="ANTHROPIC_API_KEY")
    )

# 向后兼容：保留 LLMConfig 作为全局默认配置
class LLMConfig(BaseModel):
    provider: Literal["anthropic", "openai"] = "anthropic"
    model: str = "claude-opus-4-6"
    fallback_model: str | None = None
    max_tokens: int = Field(default=8192, ge=512, le=200000)
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_retries: int = Field(default=3, ge=1)

class ThresholdConfig(BaseModel):
    auto_merge_confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    human_escalation: float = Field(default=0.60, ge=0.0, le=1.0)
    risk_score_low: float = Field(default=0.30, ge=0.0, le=1.0)
    risk_score_high: float = Field(default=0.60, ge=0.0, le=1.0)

class SecuritySensitiveConfig(BaseModel):
    patterns: list[str] = Field(
        default_factory=lambda: [
            "**/auth/**", "**/security/**", "**/*secret*",
            "**/*credential*", "**/*password*", "**/*.pem", "**/*.key"
        ]
    )
    always_require_human: bool = True

class FileClassifierConfig(BaseModel):
    excluded_patterns: list[str] = Field(
        default_factory=lambda: ["**/*.lock", "**/node_modules/**", "**/.git/**"]
    )
    binary_extensions: list[str] = Field(
        default_factory=lambda: [".png", ".jpg", ".pdf", ".zip", ".tar", ".whl"]
    )
    always_take_target_patterns: list[str] = Field(default_factory=list)
    always_take_current_patterns: list[str] = Field(default_factory=list)
    security_sensitive: SecuritySensitiveConfig = Field(default_factory=SecuritySensitiveConfig)

class OutputConfig(BaseModel):
    directory: str = "./outputs"
    formats: list[Literal["json", "markdown"]] = ["json", "markdown"]
    include_raw_diffs: bool = False
    include_llm_traces: bool = False

class MergeConfig(BaseModel):
    upstream_ref: str = Field(..., description="上游分支 ref，如 upstream/main")
    fork_ref: str = Field(..., description="下游分支 ref，如 feature/my-fork")
    working_branch: str = Field(
        default="merge/auto-{timestamp}",
        description="执行合并的工作分支名称模板"
    )
    repo_path: str = Field(default=".", description="本地仓库路径")
    project_context: str = Field(
        default="",
        description="项目背景描述，帮助 LLM 理解代码语义"
    )
    max_files_per_run: int = Field(default=500, ge=1)
    max_plan_revision_rounds: int = Field(default=2, ge=1, le=5)
    # 注意：已移除 human_decision_timeout_hours。
    # 系统不提供超时默认决策，人工裁决必须显式完成。
    llm: LLMConfig = Field(default_factory=LLMConfig)        # 全局默认，被 agents 配置覆盖
    agents: AgentsLLMConfig = Field(default_factory=AgentsLLMConfig)  # 各 Agent 独立配置
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    file_classifier: FileClassifierConfig = Field(default_factory=FileClassifierConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    @field_validator("upstream_ref", "fork_ref")
    @classmethod
    def ref_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Git ref cannot be empty")
        return v.strip()
```

### TypeScript

```typescript
interface LLMConfig {
  provider: "anthropic" | "openai";
  model: string;
  fallbackModel?: string;
  maxTokens: number;
  temperature: number;
  maxRetries: number;
}

interface ThresholdConfig {
  autoMergeConfidence: number;
  humanEscalation: number;
  riskScoreLow: number;
  riskScoreHigh: number;
}

interface MergeConfig {
  upstreamRef: string;
  forkRef: string;
  workingBranch: string;
  repoPath: string;
  projectContext: string;
  maxFilesPerRun: number;
  humanDecisionTimeoutHours?: number;
  llm: LLMConfig;
  thresholds: ThresholdConfig;
  output: {
    directory: string;
    formats: ("json" | "markdown")[];
    includeRawDiffs: boolean;
    includeLlmTraces: boolean;
  };
}
```

---

## 2. FileDiff — 文件差异分类

描述单个文件在两个分支之间的差异信息。

### Python (Pydantic v2)

```python
from enum import Enum

class FileStatus(str, Enum):
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"
    RENAMED = "renamed"
    BINARY = "binary"

class RiskLevel(str, Enum):
    AUTO_SAFE = "auto_safe"
    AUTO_RISKY = "auto_risky"
    HUMAN_REQUIRED = "human_required"
    DELETED_ONLY = "deleted_only"
    BINARY = "binary"
    EXCLUDED = "excluded"

class DiffHunk(BaseModel):
    hunk_id: str
    start_line_current: int
    end_line_current: int
    start_line_target: int
    end_line_target: int
    content_current: str       # 当前分支（fork）的内容
    content_target: str        # 目标分支（upstream）的内容
    content_base: str | None   # 共同祖先的内容（三向 diff）
    has_conflict: bool
    conflict_marker_lines: list[int] = Field(default_factory=list)

class FileDiff(BaseModel):
    file_path: str
    file_status: FileStatus
    risk_level: RiskLevel
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_factors: list[str] = Field(default_factory=list)
    lines_added: int = 0
    lines_deleted: int = 0
    lines_changed: int = 0
    conflict_count: int = 0
    hunks: list[DiffHunk] = Field(default_factory=list)
    is_security_sensitive: bool = False
    language: str | None = None    # 编程语言，用于语义分析
    raw_diff: str | None = None
```

### TypeScript

```typescript
type FileStatus = "added" | "deleted" | "modified" | "renamed" | "binary";
type RiskLevel = "auto_safe" | "auto_risky" | "human_required" | "deleted_only" | "binary" | "excluded";

interface DiffHunk {
  hunkId: string;
  startLineCurrent: number;
  endLineCurrent: number;
  startLineTarget: number;
  endLineTarget: number;
  contentCurrent: string;
  contentTarget: string;
  contentBase?: string;
  hasConflict: boolean;
  conflictMarkerLines: number[];
}

interface FileDiff {
  filePath: string;
  fileStatus: FileStatus;
  riskLevel: RiskLevel;
  riskScore: number;
  riskFactors: string[];
  linesAdded: number;
  linesDeleted: number;
  linesChanged: number;
  conflictCount: number;
  hunks: DiffHunk[];
  isSecuritySensitive: boolean;
  language?: string;
  rawDiff?: string;
}
```

---

## 3. ConflictPoint — 冲突点分析结果

ConflictAnalyst Agent 对单个冲突 Hunk 的深度语义分析结果。

### Python (Pydantic v2)

```python
class ConflictType(str, Enum):
    CONCURRENT_MODIFICATION = "concurrent_modification"  # 双方同时修改同一区域
    LOGIC_CONTRADICTION = "logic_contradiction"          # 逻辑互斥，无法共存
    SEMANTIC_EQUIVALENT = "semantic_equivalent"          # 语义等价，写法不同
    DEPENDENCY_UPDATE = "dependency_update"              # 依赖版本冲突
    INTERFACE_CHANGE = "interface_change"                # 接口签名变更
    DELETION_VS_MODIFICATION = "deletion_vs_modification"  # 一方删除一方修改
    REFACTOR_VS_FEATURE = "refactor_vs_feature"         # 重构与功能添加冲突
    CONFIGURATION = "configuration"                      # 配置值冲突
    UNKNOWN = "unknown"

class ChangeIntent(BaseModel):
    description: str           # 对修改意图的自然语言描述
    intent_type: str           # bugfix / refactor / feature / upgrade / config
    confidence: float = Field(ge=0.0, le=1.0)

class ConflictPoint(BaseModel):
    conflict_id: str           # UUID
    file_path: str
    hunk_id: str               # 关联的 DiffHunk.hunk_id
    conflict_type: ConflictType
    upstream_intent: ChangeIntent     # 上游修改的意图分析
    fork_intent: ChangeIntent         # 下游（fork）修改的意图分析
    can_coexist: bool                 # 两个修改是否可以共存
    suggested_decision: "MergeDecision"
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str             # 分析推理说明
    risk_factors: list[str] = Field(default_factory=list)
    similar_conflicts: list[str] = Field(default_factory=list)  # 相似冲突的 conflict_id
```

### TypeScript

```typescript
type ConflictType =
  | "concurrent_modification"
  | "logic_contradiction"
  | "semantic_equivalent"
  | "dependency_update"
  | "interface_change"
  | "deletion_vs_modification"
  | "refactor_vs_feature"
  | "configuration"
  | "unknown";

interface ChangeIntent {
  description: string;
  intentType: string;
  confidence: number;
}

interface ConflictPoint {
  conflictId: string;
  filePath: string;
  hunkId: string;
  conflictType: ConflictType;
  upstreamIntent: ChangeIntent;
  forkIntent: ChangeIntent;
  canCoexist: boolean;
  suggestedDecision: MergeDecision;
  confidence: number;
  rationale: string;
  riskFactors: string[];
  similarConflicts: string[];
}
```

---

## 4. MergeDecision — 合并决策枚举

系统中所有合并动作的标准化枚举。

### Python

```python
class MergeDecision(str, Enum):
    TAKE_CURRENT = "take_current"
    """保留下游（fork）版本，完全舍弃上游变更。
    适用场景：下游有必须保留的私有逻辑，上游变更在当前环境不适用。"""

    TAKE_TARGET = "take_target"
    """采用上游版本，覆盖下游变更。
    适用场景：下游仅做了格式化/注释等无意义修改，上游有重要 bugfix 或重构。"""

    SEMANTIC_MERGE = "semantic_merge"
    """语义合并：由 LLM 将双方变更合理融合。
    适用场景：双方修改互不冲突但在同一代码区域，可以共同保留。"""

    MANUAL_PATCH = "manual_patch"
    """人工提供自定义合并内容（完整替换该文件或区域的内容）。
    适用场景：LLM 无法准确合并，需要开发者手写正确版本。"""

    ESCALATE_HUMAN = "escalate_human"
    """升级到人工决策队列，系统无法自动处理。
    适用场景：置信度低于阈值，或存在逻辑矛盾，需要了解业务背景的人决策。"""

    SKIP = "skip"
    """跳过此文件，不进行任何合并操作。
    适用场景：二进制文件、已排除的文件，或人工明确决定暂不处理。"""
```

### TypeScript

```typescript
type MergeDecision =
  | "take_current"    // 保留 fork 版本
  | "take_target"     // 采用 upstream 版本
  | "semantic_merge"  // LLM 语义合并
  | "manual_patch"    // 人工提供内容
  | "escalate_human"  // 升级人工决策
  | "skip";           // 跳过此文件
```

---

## 5. FileDecisionRecord — 文件完整决策记录

Executor 执行完成后，每个文件的完整决策和操作记录。是审计链的核心数据结构。

### Python (Pydantic v2)

```python
class DecisionSource(str, Enum):
    AUTO_PLANNER = "auto_planner"          # Planner 自动决策（无冲突）
    AUTO_EXECUTOR = "auto_executor"        # Executor 基于 LLM 分析自动决策
    HUMAN = "human"                        # 人工决策
    BATCH_HUMAN = "batch_human"            # 批量人工决策
    # 注意：已移除 TIMEOUT_DEFAULT。系统禁止以超时默认策略替代人工裁决。

class FileDecisionRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    file_path: str
    file_status: FileStatus
    decision: MergeDecision
    decision_source: DecisionSource
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str
    applied_patch: str | None = None       # 实际应用的 patch 内容
    original_snapshot: str | None = None   # 合并前的文件内容快照（用于回滚）
    merged_content_preview: str | None = None  # 合并后内容的前 50 行预览
    discarded_content: str | None = None   # 被丢弃的代码（不丢失原则）
    discard_reason: str | None = None      # 丢弃原因说明
    conflict_points_resolved: list[str] = Field(default_factory=list)  # conflict_id 列表
    human_notes: str | None = None
    phase: "MergePhase"
    agent: "AgentType"
    timestamp: datetime
    is_rolled_back: bool = False
    rollback_reason: str | None = None
```

### TypeScript

```typescript
type DecisionSource =
  | "auto_planner"
  | "auto_executor"
  | "human"
  | "batch_human"
  | "timeout_default";

interface FileDecisionRecord {
  recordId: string;
  filePath: string;
  fileStatus: FileStatus;
  decision: MergeDecision;
  decisionSource: DecisionSource;
  confidence?: number;
  rationale: string;
  appliedPatch?: string;
  originalSnapshot?: string;
  mergedContentPreview?: string;
  discardedContent?: string;
  discardReason?: string;
  conflictPointsResolved: string[];
  humanNotes?: string;
  phase: MergePhase;
  agent: AgentType;
  timestamp: string;  // ISO 8601
  isRolledBack: boolean;
  rollbackReason?: string;
}
```

---

## 6. MergePlan — 阶段化合并计划

Planner Agent 的核心输出，定义整个合并流程的执行蓝图。

### Python (Pydantic v2)

```python
class MergePhase(str, Enum):
    ANALYSIS = "analysis"
    PLAN_REVIEW = "plan_review"          # Phase 1.5：PlannerJudge 审查计划
    PLAN_REVISING = "plan_revising"      # Planner 按 PlannerJudge 意见修订
    AUTO_MERGE = "auto_merge"
    CONFLICT_ANALYSIS = "conflict_analysis"
    HUMAN_REVIEW = "human_review"
    JUDGE_REVIEW = "judge_review"
    REPORT = "report"

class PhaseFileBatch(BaseModel):
    batch_id: str
    phase: MergePhase
    file_paths: list[str]
    risk_level: RiskLevel
    estimated_duration_minutes: float | None = None
    can_parallelize: bool = True

class RiskSummary(BaseModel):
    total_files: int
    auto_safe_count: int
    auto_risky_count: int
    human_required_count: int
    deleted_only_count: int
    binary_count: int
    excluded_count: int
    estimated_auto_merge_rate: float = Field(ge=0.0, le=1.0)
    top_risk_files: list[str] = Field(default_factory=list)  # 最高风险文件列表（Top 10）

class MergePlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime
    upstream_ref: str
    fork_ref: str
    merge_base_commit: str    # git merge-base 结果
    phases: list[PhaseFileBatch]
    risk_summary: RiskSummary
    project_context_summary: str  # LLM 对项目背景的理解摘要
    special_instructions: list[str] = Field(default_factory=list)
    version: str = "1.0"
```

### TypeScript

```typescript
type MergePhase =
  | "analysis"
  | "auto_merge"
  | "conflict_analysis"
  | "human_review"
  | "judge_review"
  | "report";

interface PhaseFileBatch {
  batchId: string;
  phase: MergePhase;
  filePaths: string[];
  riskLevel: RiskLevel;
  estimatedDurationMinutes?: number;
  canParallelize: boolean;
}

interface RiskSummary {
  totalFiles: number;
  autoSafeCount: number;
  autoRiskyCount: number;
  humanRequiredCount: number;
  deletedOnlyCount: number;
  binaryCount: number;
  excludedCount: number;
  estimatedAutoMergeRate: number;
  topRiskFiles: string[];
}

interface MergePlan {
  planId: string;
  createdAt: string;
  upstreamRef: string;
  forkRef: string;
  mergeBaseCommit: string;
  phases: PhaseFileBatch[];
  riskSummary: RiskSummary;
  projectContextSummary: string;
  specialInstructions: string[];
  version: string;
}
```

---

## 7. JudgeVerdict — 审查结论

Judge Agent 输出的审查裁决结果。

### Python (Pydantic v2)

```python
class VerdictType(str, Enum):
    PASS = "pass"
    CONDITIONAL = "conditional"
    FAIL = "fail"

class IssueLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class JudgeIssue(BaseModel):
    issue_id: str = Field(default_factory=lambda: str(uuid4()))
    file_path: str
    issue_level: IssueLevel
    issue_type: str     # missing_logic / wrong_merge / unresolved_conflict / etc.
    description: str
    affected_lines: list[int] = Field(default_factory=list)
    suggested_fix: str | None = None
    must_fix_before_merge: bool

class JudgeVerdict(BaseModel):
    verdict_id: str = Field(default_factory=lambda: str(uuid4()))
    verdict: VerdictType
    reviewed_files_count: int
    passed_files: list[str]
    failed_files: list[str]
    conditional_files: list[str]
    issues: list[JudgeIssue]
    critical_issues_count: int
    high_issues_count: int
    overall_confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    blocking_issues: list[str]   # 阻止合并推进的 issue_id 列表
    timestamp: datetime
    judge_model: str             # 使用的 LLM 模型版本
```

### TypeScript

```typescript
type VerdictType = "pass" | "conditional" | "fail";
type IssueLevel = "critical" | "high" | "medium" | "low" | "info";

interface JudgeIssue {
  issueId: string;
  filePath: string;
  issueLevel: IssueLevel;
  issueType: string;
  description: string;
  affectedLines: number[];
  suggestedFix?: string;
  mustFixBeforeMerge: boolean;
}

interface JudgeVerdict {
  verdictId: string;
  verdict: VerdictType;
  reviewedFilesCount: number;
  passedFiles: string[];
  failedFiles: string[];
  conditionalFiles: string[];
  issues: JudgeIssue[];
  criticalIssuesCount: number;
  highIssuesCount: number;
  overallConfidence: number;
  summary: string;
  blockingIssues: string[];
  timestamp: string;
  judgeModel: string;
}
```

---

## 8. HumanDecisionRequest — 人类裁决请求

HumanInterface Agent 向人工决策者呈现的单个裁决请求。

### Python (Pydantic v2)

```python
class DecisionOption(BaseModel):
    option_key: str              # A / B / C / custom
    decision: MergeDecision
    description: str
    preview_content: str | None  # 选择此项后的代码预览
    risk_warning: str | None

class HumanDecisionRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    file_path: str
    priority: int = Field(ge=1, le=10)   # 1 = 最高优先级
    conflict_points: list[ConflictPoint]
    context_summary: str         # 面向人工的简洁问题描述
    upstream_change_summary: str
    fork_change_summary: str
    analyst_recommendation: MergeDecision
    analyst_confidence: float
    analyst_rationale: str
    options: list[DecisionOption]
    related_files: list[str] = Field(default_factory=list)  # 相关联的其他文件
    deadline: datetime | None = None
    created_at: datetime
    # 以下字段由人工填写
    human_decision: MergeDecision | None = None
    custom_content: str | None = None    # MANUAL_PATCH 时填写
    reviewer_name: str | None = None
    reviewer_notes: str | None = None
    decided_at: datetime | None = None
    is_batch_decision: bool = False
```

### TypeScript

```typescript
interface DecisionOption {
  optionKey: string;
  decision: MergeDecision;
  description: string;
  previewContent?: string;
  riskWarning?: string;
}

interface HumanDecisionRequest {
  requestId: string;
  filePath: string;
  priority: number;
  conflictPoints: ConflictPoint[];
  contextSummary: string;
  upstreamChangeSummary: string;
  forkChangeSummary: string;
  analystRecommendation: MergeDecision;
  analystConfidence: number;
  analystRationale: string;
  options: DecisionOption[];
  relatedFiles: string[];
  deadline?: string;
  createdAt: string;
  humanDecision?: MergeDecision;
  customContent?: string;
  reviewerName?: string;
  reviewerNotes?: string;
  decidedAt?: string;
  isBatchDecision: boolean;
}
```

---

## 9. MergeState — 全局状态机状态

系统的核心数据容器，贯穿整个合并流程，支持序列化为 JSON 用于断点续传。

### Python (Pydantic v2)

```python
class SystemStatus(str, Enum):
    INITIALIZED = "initialized"
    PLANNING = "planning"
    PLAN_REVIEWING = "plan_reviewing"          # PlannerJudge 审查中
    PLAN_REVISING = "plan_revising"            # Planner 修订计划中
    AUTO_MERGING = "auto_merging"
    PLAN_DISPUTE_PENDING = "plan_dispute_pending"  # Executor 发起质疑，等待 Planner 修订
    ANALYZING_CONFLICTS = "analyzing_conflicts"
    AWAITING_HUMAN = "awaiting_human"
    JUDGE_REVIEWING = "judge_reviewing"
    GENERATING_REPORT = "generating_report"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

class PhaseResult(BaseModel):
    phase: MergePhase
    status: Literal["pending", "running", "completed", "failed", "skipped"]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

class MergeState(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    config: MergeConfig
    status: SystemStatus = SystemStatus.INITIALIZED
    current_phase: MergePhase = MergePhase.ANALYSIS
    phase_results: dict[MergePhase, PhaseResult] = Field(default_factory=dict)

    # Planner 输出
    merge_plan: MergePlan | None = None
    file_classifications: dict[str, RiskLevel] = Field(default_factory=dict)
    plan_revision_rounds: int = 0   # 当前计划修订轮次

    # PlannerJudge 输出
    plan_judge_verdict: "PlanJudgeVerdict | None" = None

    # Executor 输出（含 Plan Dispute）
    file_decision_records: dict[str, FileDecisionRecord] = Field(default_factory=dict)
    applied_patches: list[str] = Field(default_factory=list)
    plan_disputes: list["PlanDisputeRequest"] = Field(default_factory=list)  # Executor 发起的质疑

    # ConflictAnalyst 输出
    conflict_analyses: dict[str, "ConflictAnalysis"] = Field(default_factory=dict)

    # HumanInterface 输出
    human_decision_requests: dict[str, HumanDecisionRequest] = Field(default_factory=dict)
    human_decisions: dict[str, MergeDecision] = Field(default_factory=dict)

    # Judge 输出
    judge_verdict: JudgeVerdict | None = None

    # 错误与日志
    errors: list[dict] = Field(default_factory=list)
    messages: list["AgentMessage"] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    checkpoint_path: str | None = None

    class Config:
        use_enum_values = True
```

### TypeScript

```typescript
type SystemStatus =
  | "initialized" | "planning" | "auto_merging"
  | "analyzing_conflicts" | "awaiting_human" | "judge_reviewing"
  | "generating_report" | "completed" | "failed" | "paused";

interface MergeState {
  runId: string;
  config: MergeConfig;
  status: SystemStatus;
  currentPhase: MergePhase;
  phaseResults: Record<MergePhase, { status: string; startedAt?: string; completedAt?: string; error?: string }>;
  mergePlan?: MergePlan;
  fileClassifications: Record<string, RiskLevel>;
  conflictAnalyses: Record<string, ConflictAnalysis>;
  fileDecisionRecords: Record<string, FileDecisionRecord>;
  appliedPatches: string[];
  humanDecisionRequests: Record<string, HumanDecisionRequest>;
  humanDecisions: Record<string, MergeDecision>;
  judgeVerdict?: JudgeVerdict;
  errors: Array<{ timestamp: string; phase: string; message: string; details?: unknown }>;
  createdAt: string;
  updatedAt: string;
  checkpointPath?: string;
}
```

---

## 10. PlanJudgeVerdict — 计划审查结论

PlannerJudge Agent 对 MergePlan 的审查裁决。

### Python (Pydantic v2)

```python
class PlanJudgeResult(str, Enum):
    APPROVED = "approved"              # 计划质量合格，进入执行阶段
    REVISION_NEEDED = "revision_needed"  # 有具体问题，要求 Planner 修订
    CRITICAL_REPLAN = "critical_replan"  # 计划根本性缺陷，要求完整重规划

class PlanIssue(BaseModel):
    issue_id: str = Field(default_factory=lambda: str(uuid4()))
    file_path: str                     # 被质疑的文件路径
    current_classification: RiskLevel  # 当前分类
    suggested_classification: RiskLevel  # 建议分类
    reason: str                        # 质疑理由（具体而非模糊）
    issue_type: str  # risk_underestimated / wrong_batch / missing_dependency / security_missed

class PlanJudgeVerdict(BaseModel):
    verdict_id: str = Field(default_factory=lambda: str(uuid4()))
    result: PlanJudgeResult
    revision_round: int = 0            # 当前是第几轮修订（0 = 初次审查）
    issues: list[PlanIssue] = Field(default_factory=list)
    approved_files_count: int = 0
    flagged_files_count: int = 0
    summary: str
    judge_model: str                   # 使用的 LLM 模型
    timestamp: datetime
```

### TypeScript

```typescript
type PlanJudgeResult = "approved" | "revision_needed" | "critical_replan";

interface PlanIssue {
  issueId: string;
  filePath: string;
  currentClassification: RiskLevel;
  suggestedClassification: RiskLevel;
  reason: string;
  issueType: string;
}

interface PlanJudgeVerdict {
  verdictId: string;
  result: PlanJudgeResult;
  revisionRound: number;
  issues: PlanIssue[];
  approvedFilesCount: number;
  flaggedFilesCount: number;
  summary: string;
  judgeModel: string;
  timestamp: string;
}
```

---

## 11. PlanDisputeRequest — Executor 计划质疑

Executor 在执行过程中发现计划问题时，向 Orchestrator 提交的质疑请求。

### Python (Pydantic v2)

```python
class PlanDisputeRequest(BaseModel):
    dispute_id: str = Field(default_factory=lambda: str(uuid4()))
    raised_by: AgentType = AgentType.EXECUTOR
    phase: MergePhase
    disputed_files: list[str]          # 质疑哪些文件的分类
    dispute_reason: str                # 具体问题描述（不允许模糊描述）
    suggested_reclassification: dict[str, RiskLevel]  # 建议的重新分类
    impact_assessment: str             # 若按原计划执行，预期风险
    evidence: str | None = None        # 支持质疑的代码片段或 diff 摘录
    timestamp: datetime = Field(default_factory=datetime.now)
    resolved: bool = False
    resolution_summary: str | None = None  # 处理结果说明
```

### TypeScript

```typescript
interface PlanDisputeRequest {
  disputeId: string;
  raisedBy: AgentType;
  phase: MergePhase;
  disputedFiles: string[];
  disputeReason: string;
  suggestedReclassification: Record<string, RiskLevel>;
  impactAssessment: string;
  evidence?: string;
  timestamp: string;
  resolved: boolean;
  resolutionSummary?: string;
}
```

---

## 12. AgentMessage — Agent 间消息

Agent 间通过 MessageBus 传递的标准化消息格式。

### Python (Pydantic v2)

```python
class AgentType(str, Enum):
    PLANNER = "planner"
    PLANNER_JUDGE = "planner_judge"    # 新增：计划质量审查 Agent
    CONFLICT_ANALYST = "conflict_analyst"
    EXECUTOR = "executor"
    JUDGE = "judge"
    HUMAN_INTERFACE = "human_interface"
    ORCHESTRATOR = "orchestrator"
    BROADCAST = "broadcast"

class MessageType(str, Enum):
    INFO = "info"                     # 普通信息通知
    REQUEST = "request"               # 请求另一 Agent 执行操作
    RESPONSE = "response"             # 对 REQUEST 的回复
    STATE_UPDATE = "state_update"     # 状态变更通知
    ERROR = "error"                   # 错误报告
    PHASE_COMPLETED = "phase_completed"
    HUMAN_INPUT_NEEDED = "human_input_needed"
    HUMAN_INPUT_RECEIVED = "human_input_received"

class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    sender: AgentType
    receiver: AgentType
    phase: MergePhase
    message_type: MessageType
    subject: str                     # 消息主题（简短描述）
    payload: dict = Field(default_factory=dict)  # 消息内容（类型根据 message_type 而异）
    correlation_id: str | None = None  # 关联的 REQUEST 消息 ID
    priority: int = Field(default=5, ge=1, le=10)
    timestamp: datetime = Field(default_factory=datetime.now)
    is_processed: bool = False
    processing_error: str | None = None
```

### TypeScript

```typescript
type AgentType =
  | "planner" | "conflict_analyst" | "executor"
  | "judge" | "human_interface" | "orchestrator" | "broadcast";

type MessageType =
  | "info" | "request" | "response" | "state_update"
  | "error" | "phase_completed" | "human_input_needed" | "human_input_received";

interface AgentMessage {
  messageId: string;
  sender: AgentType;
  receiver: AgentType;
  phase: MergePhase;
  messageType: MessageType;
  subject: string;
  payload: Record<string, unknown>;
  correlationId?: string;
  priority: number;
  timestamp: string;
  isProcessed: boolean;
  processingError?: string;
}
```
