# Agent 设计文档

## 目录

1. [Agent 总览](#1-agent-总览)
2. [Agent 详细职责](#2-agent-详细职责)
3. [Agent 间通信协议](#3-agent-间通信协议)
4. [Agent 调度机制](#4-agent-调度机制)
5. [输入/输出规范](#5-输入输出规范)
6. [审查隔离保证](#6-审查隔离保证)
7. [Human-in-the-loop 机制](#7-human-in-the-loop-机制)
8. [开源项目参考映射](#8-开源项目参考映射)

---

## 1. Agent 总览

| Agent | 角色 | 写权限 | LLM 使用 | 触发 Phase |
|-------|------|--------|----------|-----------|
| **Planner** | 分析 diff，制定分阶段合并计划 | 否（只读 Git） | 高频 | Phase 1，以及被 Executor 触发的计划修订 |
| **PlannerJudge** | 独立审查 Planner 输出的计划质量 | 否（强制只读） | 中频 | Phase 1.5 |
| **ConflictAnalyst** | 深度分析高风险冲突，给出合并建议 | 否 | 高频 | Phase 3 |
| **Executor** | 执行自动合并，生成 patch 并应用 | 是（写文件/Git） | 中频 | Phase 2, 3；可发起计划质疑 |
| **Judge/Reviewer** | 只读审查合并结果，输出裁决报告 | 否（强制只读） | 中频 | Phase 5 |
| **HumanInterface** | 收集人工决策，结构化呈现待裁决项 | 否 | 低频 | Phase 4 |

---

### 1.1 各 Agent LLM 配置

每个 Agent 支持独立配置 LLM 提供商和模型，允许将执行者与审查者配置为不同模型，形成有效的双重验证。

```yaml
agents:
  planner:
    provider: anthropic          # anthropic | openai
    model: claude-opus-4-6       # 规划需要最强推理能力
    temperature: 0.2
    max_tokens: 8192

  planner_judge:
    provider: openai             # 与 Planner 使用不同提供商，避免同源偏差
    model: gpt-4o
    temperature: 0.1
    max_tokens: 4096

  conflict_analyst:
    provider: anthropic
    model: claude-sonnet-4-6     # 平衡速度与分析深度
    temperature: 0.3
    max_tokens: 8192

  executor:
    provider: openai
    model: gpt-4o
    temperature: 0.1             # 低温度，执行需要确定性
    max_tokens: 16384

  judge:
    provider: anthropic          # 与 Executor 使用不同提供商
    model: claude-opus-4-6       # 最终审查使用最强模型
    temperature: 0.1
    max_tokens: 8192

  human_interface:
    provider: anthropic
    model: claude-haiku-4-5-20251001   # 报告生成，轻量即可
    temperature: 0.2
    max_tokens: 4096
```

**设计原则**：
- Planner 与 PlannerJudge 建议使用**不同提供商**，避免同源模型产生相同盲区。
- Executor 与 Judge 同理，保证审查视角独立。
- 所有配置通过环境变量注入密钥，绝不在配置文件中硬编码。

```python
class AgentLLMConfig(BaseModel):
    provider: Literal["anthropic", "openai"]
    model: str
    temperature: float = 0.2
    max_tokens: int = 8192
    api_key_env: str   # 环境变量名，如 "ANTHROPIC_API_KEY"

class LLMClientFactory:
    @staticmethod
    def create(config: AgentLLMConfig) -> LLMClient:
        api_key = os.environ.get(config.api_key_env)
        if not api_key:
            raise EnvironmentError(f"Missing env var: {config.api_key_env}")
        if config.provider == "anthropic":
            return AnthropicClient(api_key=api_key, model=config.model)
        elif config.provider == "openai":
            return OpenAIClient(api_key=api_key, model=config.model)
```

---

## 2. Agent 详细职责

### 2.1 Planner Agent

**核心职责**：充当系统的"战略规划者"。在合并流程启动时，Planner 分析两个分支之间的完整 diff，将所有变更文件分类为不同风险等级，并生成一个结构化的 `MergePlan`，指导后续所有 Agent 的执行顺序。

**具体任务**：

1. 调用 `git diff <upstream>..<fork>` 获取全量差异文件列表。
2. 对每个文件调用 `FileClassifier` 计算风险分数（0.0 ~ 1.0）。
3. 将文件分类为：
   - `AUTO_SAFE`（风险 < 0.3）：可直接自动合并
   - `AUTO_RISKY`（0.3 ≤ 风险 < 0.6）：自动合并但需 Judge 审查
   - `HUMAN_REQUIRED`（风险 ≥ 0.6）：必须人工参与决策
   - `DELETED_ONLY`：仅有删除操作，需确认是否保留
   - `BINARY`：二进制文件，特殊处理
4. 使用 LLM 分析 `HUMAN_REQUIRED` 类文件的冲突性质，生成初步描述。
5. 输出 `MergePlan`，包含各 Phase 的文件分配和执行顺序。

**关键约束**：
- Planner 不修改任何文件，只生成计划。
- 若 diff 文件总数超过 `config.max_files_per_run`，Planner 将自动分批生成多个子计划。

---

### 2.2 ConflictAnalyst Agent

**核心职责**：对 Planner 标记的高风险冲突文件进行深度语义分析，理解每个冲突点的"上游修改意图"和"下游修改意图"，生成带有置信度的合并建议。

**具体任务**：

1. 接收 `MergePlan` 中 `HUMAN_REQUIRED` 和 `AUTO_RISKY` 文件列表。
2. 对每个文件，提取三向 diff（base、current、target）。
3. 使用 LLM 分析每个 `ConflictPoint`：
   - 判断修改是否功能等价（语义相同但写法不同）
   - 识别上游修改的目的（bugfix / refactor / feature / dependency upgrade）
   - 识别下游修改的目的（custom logic / hotfix / configuration）
   - 评估两者是否可以共存
4. 为每个冲突点输出：
   - `suggested_resolution`：推荐的合并方式
   - `confidence`：置信度（0.0 ~ 1.0）
   - `rationale`：推理说明
   - `risk_factors`：风险因素列表
5. 置信度 < `config.auto_merge_confidence_threshold` 的冲突标记为 `ESCALATE_HUMAN`。

**关键约束**：
- ConflictAnalyst 不写文件，只输出分析报告。
- 分析结果存入 `MergeState.conflict_analyses`，供 Executor 和 HumanInterface 读取。

---

### 2.3 Executor Agent

**核心职责**：系统中唯一具有写权限的 Agent。根据 `MergePlan` 和 `ConflictAnalyst` 的分析结果，执行具体的代码合并操作。Executor 在执行过程中若发现计划存在问题，有权发起计划质疑，触发 Planner 重新分析。

**具体任务**：

1. **Phase 2（低风险自动合并）**：
   - 读取 `AUTO_SAFE` 文件的合并策略（通常为 `TAKE_TARGET` 或 `SEMANTIC_MERGE`）。
   - 对每个文件生成合并后的内容（必要时调用 LLM 辅助语义合并）。
   - 生成标准 git patch 文件。
   - 调用 `patch_applier.apply_patch()` 原子性写入工作区。
   - 记录每个文件的 `FileDecisionRecord`。

2. **Phase 3（高风险合并，已有 ConflictAnalyst 建议）**：
   - 读取置信度满足阈值的 `ConflictAnalysis`。
   - 按建议策略生成合并 patch。
   - 应用前先保存原始文件快照（用于回滚）。
   - 应用 patch，记录 `FileDecisionRecord`。

3. **应用人工决策（Phase 4 之后）**：
   - 读取 `HumanDecisionRequest` 的已填写结果。
   - 按人工指定的策略执行合并操作。

4. **计划质疑机制（Plan Dispute）**：

   Executor 在实际处理文件时，若发现以下情况，**必须暂停当前文件处理，向 Orchestrator 发起计划质疑**：
   - 被标记为 `AUTO_SAFE` 的文件，打开后发现包含认证/权限/数据模型等高敏感逻辑
   - 一个 Phase 批次中的多个文件存在强耦合，拆分处理会导致中间状态不一致
   - 文件的实际 diff 复杂程度远超 Planner 的风险评估（如 `AUTO_SAFE` 文件实际有大量语义冲突）
   - 发现 Planner 未识别到的重命名/移动文件关系

   质疑流程：
   ```python
   class PlanDisputeRequest(BaseModel):
       disputed_files: list[str]       # 质疑哪些文件的分类
       dispute_reason: str             # 具体问题描述
       suggested_reclassification: dict[str, FileRiskLevel]  # 建议的重新分类
       impact_assessment: str          # 若按原计划执行，可能导致的风险

   # Executor 发起质疑后：
   # 1. 暂停当前批次中受影响文件的处理
   # 2. 将 PlanDisputeRequest 写入 MergeState.plan_disputes
   # 3. Orchestrator 检测到质疑，暂停 Phase 2/3，触发 Planner 重新分析
   # 4. Planner 针对质疑点重新分析并修订计划（不是完整重规划）
   # 5. PlannerJudge 对修订结果再次审查
   # 6. 审查通过后，Executor 继续执行（按修订后的计划）
   ```

**关键约束**：
- Executor 在 Judge 审查通过之前，所有写操作均在独立的 **工作分支**（`merge/working-branch`）上进行，不影响主分支。
- 每次写操作前必须保存快照，支持单文件级别的回滚。
- Executor 不能覆盖 `ESCALATE_HUMAN` 状态的文件，必须等待人工决策。
- Executor 发起质疑后，**不得私自提升或降低文件风险分类**，只能通过正式质疑流程请求 Planner 修订。

---

### 2.4 PlannerJudge Agent

**核心职责**：对 Planner Agent 输出的 `MergePlan` 进行独立质量审查，确保计划粒度合理、风险分类准确、无遗漏高风险文件，在计划进入执行阶段前充当"把门人"。

**设计动机**：Planner 的输出质量直接影响后续所有 Agent 的工作质量。若计划粒度过粗（如将一个包含认证逻辑的文件错分为 AUTO_SAFE），Executor 会在无充分分析的情况下直接合并，造成静默风险。PlannerJudge 的职责是在执行前发现这类问题。

**具体任务**：

1. 接收 Planner 输出的 `MergePlan`，以**只读方式**访问原始 diff 信息。
2. 对计划进行以下维度的审查：
   - **分类准确性**：检查风险分类是否合理，有无明显低估风险的文件
   - **粒度完整性**：检查计划中是否有过于粗粒度的批次（如将高度耦合的文件分散到不同 Phase）
   - **高风险识别完整性**：比对安全敏感路径模式，验证所有安全相关文件是否都被正确标记
   - **依赖关系识别**：检查有无文件间依赖被忽略（如接口文件与实现文件应在同一批次处理）
3. 使用独立于 Planner 的 LLM（不同提供商/模型），避免同源偏差。
4. 输出 `PlanJudgeVerdict`：
   - `APPROVED`：计划质量合格，可进入 Phase 2
   - `REVISION_NEEDED`：计划有具体问题，返回修订意见给 Planner
   - `CRITICAL_REPLAN`：计划存在根本性缺陷，要求 Planner 重新完整规划

**关键约束**：
- PlannerJudge 使用 `ReadOnlyStateView`，不修改任何状态。
- PlannerJudge 的最终结论由 Orchestrator 代理写入 `MergeState.plan_judge_verdict`。
- 若 PlannerJudge 与 Planner 发生分歧，**则 PlannerJudge 与 Planner 需要讨论，直到达成一致**。
- 最多允许 `config.max_plan_revision_rounds`（默认 2）轮修订，超出后升级为人工干预。

---

### 2.5 Judge/Reviewer Agent
**核心职责**：充当独立的质量门禁。在 Executor 完成所有自动合并后，Judge 对合并结果进行全面审查，输出带有通过/有条件通过/拒绝结论的 `JudgeVerdict`。

**具体任务**：

1. 读取工作分支上所有已合并文件的最终状态。
2. 读取所有 `FileDecisionRecord`，检查决策记录的完整性。
3. 对每个高风险文件进行二次语义审查：
   - 验证合并结果是否保留了下游私有逻辑。
   - 验证合并结果是否正确引入了上游新功能。
   - 检查是否有遗漏的冲突标记（`<<<<<<`）。
4. 执行静态检查：
   - 语法有效性（可选，通过外部工具）
   - 关键接口签名是否发生意外变更
5. 汇总所有审查结果，输出：
   - `PASS`：批准，可推进到报告生成阶段
   - `CONDITIONAL`：有条件通过，列出必须修复的问题
   - `FAIL`：拒绝，需要重新进行冲突分析或人工干预

**关键约束**：
- Judge 使用 **只读文件系统接口**（`ReadOnlyFileSystem`），在代码层面被阻止写入任何文件。
- Judge 的审查结论是推进到 Phase 6 的必要条件。
- Judge 与 Executor 使用不同的 LLM Prompt 模板，确保视角独立。

---

### 2.6 HumanInterface Agent

**核心职责**：作为系统与人工决策者之间的接口，将需要人工裁决的冲突结构化呈现，收集决策结果，将其转换为系统可处理的 `FileDecisionRecord`。

**具体任务**：

1. 汇总所有 `ESCALATE_HUMAN` 状态的 `ConflictPoint`。
2. 按优先级排序（影响范围大、风险高的先呈现）。
3. 生成 `HumanReport`：
   - Markdown 格式，人类可直接阅读
   - 每个冲突项包含：文件路径、冲突代码对比、ConflictAnalyst 的分析摘要、推荐选项列表
4. 等待人工填写决策（CLI 交互模式或文件回写模式）。
5. 验证人工决策的合法性（枚举值、必填字段）。
6. 将验证通过的决策写入 `MergeState.human_decisions`，触发 Executor 继续执行。

**支持的输入模式**：
- **CLI 交互模式**：逐项引导用户在终端输入决策。
- **文件批注模式**：生成带有注释的 YAML 文件，用户填写后由 `merge resume` 命令读取。
- **HTTP API 模式**（可选扩展）：启动本地 Web 服务，提供表单界面供用户决策。

---

## 3. Agent 间通信协议

### 3.1 消息结构

所有 Agent 间通信使用 `AgentMessage` 对象：

```python
class AgentMessage(BaseModel):
    message_id: str           # UUID，唯一标识
    sender: AgentType         # 发送方 Agent 枚举
    receiver: AgentType       # 接收方 Agent 枚举（或 BROADCAST）
    phase: MergePhase         # 消息所属 Phase
    message_type: MessageType # INFO / REQUEST / RESPONSE / ERROR / STATE_UPDATE
    payload: dict             # 消息内容，结构因 message_type 而异
    timestamp: datetime
    correlation_id: str | None  # 关联的请求消息 ID（用于 REQUEST-RESPONSE 配对）
```

### 3.2 通信模式

系统使用**基于共享状态的间接通信**，而非直接点对点调用：

```
Agent A ──write──> MergeState ──read──> Agent B
                       │
                   MessageBus（可选订阅通知）
```

- **主数据通道**：`MergeState` 对象，所有 Agent 读取和写入统一状态。
- **事件通知**：`MessageBus` 用于发布状态变更事件（如 `PHASE_COMPLETED`、`HUMAN_DECISION_NEEDED`）。
- **审查隔离**：Judge 只通过 `ReadOnlyStateView` 访问状态，该视图在运行时拦截所有写操作。

### 3.3 状态写入规则

| Agent | 可写入的状态字段 |
|-------|----------------|
| Planner | `merge_plan`, `file_classifications` |
| PlannerJudge | `plan_judge_verdict`（唯一例外，由 Orchestrator 代理写入） |
| ConflictAnalyst | `conflict_analyses` |
| Executor | `applied_patches`, `file_decision_records`, `plan_disputes` |
| Judge | `judge_verdict`（唯一例外，由 Orchestrator 代理写入） |
| HumanInterface | `human_decisions` |

---

## 4. Agent 调度机制

### 4.1 Orchestrator 模式

系统采用**集中式 Orchestrator 调度模式**，而非去中心化的 Agent 自主调度：

```
Orchestrator
    │
    ├── Phase 1:   [Planner]                          → 生成 MergePlan
    ├── Phase 1.5: [PlannerJudge]                     → 审查计划质量
    │               ├── APPROVED  → 进入 Phase 2
    │               ├── REVISION_NEEDED → 返回 Planner 修订（最多 2 轮）
    │               └── CRITICAL_REPLAN → Planner 完整重规划
    │
    ├── Phase 2:   [Executor] (并发处理 AUTO_SAFE 文件)
    │               └── [Plan Dispute?] → 暂停 → Planner 修订 → PlannerJudge 审查 → 继续
    │
    ├── Phase 3:   [ConflictAnalyst] → [Executor] (串行，分析后执行)
    │               └── [Plan Dispute?] → 同 Phase 2 的质疑流程
    │
    ├── Phase 4:   [HumanInterface] (阻塞等待人工输入，无超时默认策略)
    │               └── [Executor] (人工决策后继续)
    ├── Phase 5:   [Judge]
    └── Phase 6:   [Report Generator]
```

### 4.2 Phase 调度规则

```python
PHASE_SCHEDULE = {
    MergePhase.ANALYSIS: {
        "agents": [AgentType.PLANNER],
        "concurrency": "sequential",
        "required_state": None,
        "produces": "merge_plan"
    },
    MergePhase.PLAN_REVIEW: {                # 新增：计划审查 Phase
        "agents": [AgentType.PLANNER_JUDGE],
        "concurrency": "sequential",
        "required_state": "merge_plan",
        "produces": "plan_judge_verdict",
        "on_revision_needed": {
            "max_rounds": 2,                 # 最多 2 轮修订
            "fallback": "HUMAN_INTERVENTION" # 超出轮次升级人工
        }
    },
    MergePhase.AUTO_MERGE: {
        "agents": [AgentType.EXECUTOR],
        "concurrency": "parallel",
        "required_state": "plan_judge_verdict(APPROVED)",
        "file_filter": "AUTO_SAFE",
        "produces": "file_decision_records",
        "on_plan_dispute": {
            "pause_execution": True,
            "trigger": [AgentType.PLANNER, AgentType.PLANNER_JUDGE],
            "resume_after": "plan_judge_verdict(APPROVED)"
        }
    },
    MergePhase.CONFLICT_ANALYSIS: {
        "agents": [AgentType.CONFLICT_ANALYST, AgentType.EXECUTOR],
        "concurrency": "sequential_per_agent",
        "required_state": "merge_plan",
        "file_filter": "AUTO_RISKY | HUMAN_REQUIRED",
        "produces": "conflict_analyses, partial_file_decision_records",
        "on_plan_dispute": {
            "pause_execution": True,
            "trigger": [AgentType.PLANNER, AgentType.PLANNER_JUDGE],
            "resume_after": "plan_judge_verdict(APPROVED)"
        }
    },
    MergePhase.HUMAN_REVIEW: {
        "agents": [AgentType.HUMAN_INTERFACE, AgentType.EXECUTOR],
        "concurrency": "blocking",
        "required_state": "conflict_analyses",
        "file_filter": "ESCALATE_HUMAN",
        "produces": "human_decisions, remaining_file_decision_records",
        # 注意：无 timeout_default_strategy。人工决策必须显式完成，
        # 系统永远不会以默认策略代替人工裁决，防止静默误合。
    },
    MergePhase.JUDGE_REVIEW: {
        "agents": [AgentType.JUDGE],
        "concurrency": "sequential",
        "required_state": "all_file_decision_records",
        "produces": "judge_verdict"
    },
    MergePhase.REPORT: {
        "agents": [],
        "required_state": "judge_verdict(PASS or CONDITIONAL)"
    }
}
```

### 4.3 Phase 跳过与重试

- 若某 Phase 已有有效的检查点数据，Orchestrator 自动跳过该 Phase（断点续传）。
- 若 Judge 返回 `FAIL`，Orchestrator 根据失败原因决定回退到 Phase 3 或 Phase 4 重新执行。
- 回退不会清除已成功处理的文件记录，只重新处理 Judge 标记的问题文件。

---

## 5. 输入/输出规范

### 5.1 Planner Agent

**输入**：
```python
{
    "state": MergeState,          # 包含 config、git_repo 引用
    "upstream_ref": str,          # 上游分支 ref（如 "upstream/main"）
    "fork_ref": str,              # 下游分支 ref（如 "feature/my-fork"）
}
```

**输出**（写入 `MergeState.merge_plan`）：
```python
MergePlan(
    phases=[...],                 # Phase 列表，每个 Phase 包含文件分配
    total_files=int,
    risk_summary=RiskSummary,
    estimated_auto_merge_rate=float,
)
```

### 5.2 ConflictAnalyst Agent

**输入**（从 `MergeState` 读取）：
- `merge_plan.phases[CONFLICT_ANALYSIS].files`
- 每个文件的三向 diff（从 Git 获取）

**输出**（写入 `MergeState.conflict_analyses`）：
```python
{
    "file_path": ConflictAnalysis(
        conflict_points=[ConflictPoint(...)],
        overall_complexity=float,
        recommended_strategy=MergeDecision,
        confidence=float,
        rationale=str,
    )
}
```

### 5.3 Executor Agent

**输入**（从 `MergeState` 读取）：
- 当前 Phase 需要处理的文件列表
- 对应的 `ConflictAnalysis`（如存在）
- `HumanDecision`（如存在）

**输出**（写入 `MergeState.file_decision_records` + 实际文件系统）：
```python
FileDecisionRecord(
    file_path=str,
    decision=MergeDecision,
    applied_patch=str,
    original_snapshot=str,    # 原始内容快照，用于回滚
    confidence=float,
    rationale=str,
    timestamp=datetime,
    agent=AgentType.EXECUTOR,
)
```

### 5.4 Judge Agent

**输入**（只读访问 `MergeState`）：
- 所有 `file_decision_records`
- 工作分支上的已合并文件内容
- 原始 diff 信息

**输出**（写入 `MergeState.judge_verdict`）：
```python
JudgeVerdict(
    verdict=VerdictType,          # PASS / CONDITIONAL / FAIL
    reviewed_files=int,
    issues=[JudgeIssue(...)],     # 发现的问题列表
    passed_files=[str],
    failed_files=[str],
    conditional_files=[str],
    summary=str,
    timestamp=datetime,
)
```

### 5.5 HumanInterface Agent

**输入**（从 `MergeState` 读取）：
- `conflict_analyses`（所有 `ESCALATE_HUMAN` 项）

**输出（两步）**：

第一步：生成 `HumanReport`（Markdown 文件）

第二步：接收用户输入后，写入 `MergeState.human_decisions`：
```python
{
    "file_path": HumanDecision(
        file_path=str,
        decision=MergeDecision,
        custom_content=str | None,  # 若选择 MANUAL_PATCH
        reviewer_notes=str,
        timestamp=datetime,
    )
}
```

---

## 6. 审查隔离保证

### 6.1 设计思路

Judge Agent 的独立性是系统质量门禁的核心保证。若 Judge 可以修改被审查的数据，则其审查结论将失去可信度。

### 6.2 实现机制

**方案一：ReadOnlyStateView（推荐）**

```python
class ReadOnlyStateView:
    """Judge Agent 专用的只读状态视图"""

    def __init__(self, state: MergeState):
        self._state = state

    def __getattr__(self, name: str):
        value = getattr(self._state, name)
        if isinstance(value, (dict, list)):
            return deepcopy(value)  # 返回深拷贝，修改不影响原始状态
        return value

    def __setattr__(self, name: str, value):
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            raise PermissionError(
                f"Judge Agent is read-only. Attempted to write: {name}"
            )
```

**方案二：运行时权限检查**

在 `Orchestrator` 中，当调度 Judge Agent 时，传入的 `state` 参数使用 `ReadOnlyStateView` 封装：

```python
async def run_phase_judge(self, state: MergeState):
    readonly_view = ReadOnlyStateView(state)
    verdict = await self.judge_agent.run(readonly_view)
    # Judge 的唯一写权限：verdict 通过 Orchestrator 代理写入
    state.judge_verdict = verdict
```

### 6.3 Executor 写操作约束

Executor 的所有文件写操作均限制在指定工作分支：

```python
WORKING_BRANCH = "merge/auto-generated-{timestamp}"
```

- Phase 2-4 的所有 patch 应用在此分支上进行。
- 直到 Judge 返回 `PASS`，Orchestrator 才将此分支合并至目标分支。
- 若 Judge 返回 `FAIL`，可直接删除工作分支，不污染任何主要分支。

---

## 7. Human-in-the-loop 机制

### 7.1 触发条件

以下任意条件满足时，系统自动进入人工等待模式：

| 触发条件 | 说明 |
|----------|------|
| `confidence < config.human_threshold`（默认 0.6） | ConflictAnalyst 置信度不足 |
| `conflict_type == LOGIC_CONTRADICTION` | 检测到逻辑矛盾，双方修改互相排斥 |
| `file_is_security_critical` | 安全敏感文件（如认证、加密相关） |
| `human_review_required_patterns` 匹配 | 配置文件中指定的文件路径模式 |
| Executor 应用 patch 失败超过重试次数 | 自动合并执行失败 |
| Judge 返回 `FAIL` 且失败原因为 `AMBIGUOUS_INTENT` | Judge 认为意图不明确需人工裁决 |

### 7.2 人工决策流程

```
[触发 ESCALATE_HUMAN]
        │
        ▼
[HumanInterface 汇总所有待决策项]
        │
        ▼
[生成 human_report.md，包含：]
  - 文件路径与变更摘要
  - 上游意图 vs 下游意图对比
  - ConflictAnalyst 分析结论
  - 可选决策列表（带说明）
        │
        ▼
[等待人工输入]（CLI 交互 或 文件批注）
        │
        ▼
[HumanInterface 验证决策合法性]
        │
   ┌────┴────┐
合法           非法
  │              │
  ▼              ▼
写入 state    提示重新输入
  │
  ▼
[Executor 按人工决策继续执行]
```

### 7.3 等待策略（无超时默认）

**系统不提供超时默认策略。**

原因：超时后以默认策略（如 `TAKE_CURRENT`）代替人工裁决，是一种隐式决策，违反"不确定即升级"原则，极易导致上游修复被静默丢弃或下游关键逻辑被错误覆盖。

系统在 `AWAITING_HUMAN` 状态下的处理：

```python
class HumanWaitPolicy(BaseModel):
    # 超时后的行为：只允许通知，不允许自动决策
    notification_interval_hours: int = 24  # 每隔多久发送提醒通知
    max_wait_days: int | None = None       # None = 无限等待
    on_max_wait_exceeded: Literal["notify_only", "abort"] = "notify_only"
    # 禁止的配置项（强制不可配置）：
    # timeout_default_strategy: 不存在此字段
```

- 若达到提醒阈值，系统向配置的通知渠道发送提醒（CLI 输出、邮件、Webhook 等）。
- 系统**永远不会**以任何默认策略替代人工填写的决策。
- 若用户选择 `on_max_wait_exceeded: abort`，系统进入 `FAILED` 状态，保留完整检查点供后续恢复。

### 7.4 批量决策支持

对于性质相似的冲突（如同一模块下的多个文件均为"依赖版本升级冲突"），HumanInterface 支持批量决策：

```
发现 15 个文件存在相同类型的冲突：[依赖声明更新]
是否对所有此类冲突统一应用 TAKE_TARGET 策略？(y/n)
```

批量决策的每个文件仍会生成独立的 `FileDecisionRecord`，但 `decision_source` 字段标注为 `BATCH_HUMAN`。

---

## 8. 开源项目参考映射

基于 reference.md 的研究结论，各 Agent 在实现时应参考以下开源项目：

| Agent | 参考项目 | 借鉴方向 |
|-------|---------|---------|
| **ConflictAnalyst** | [weave](https://github.com/ataraxy-labs/weave) | entity-level 三方合并内核，按函数/类/JSON key 粒度做语义 merge |
| **Judge/Reviewer** | [git-regress](https://github.com/TonyStef/git-regress) | symbol footprint 比对，检测合并后的语义回归（如符号被静默删除） |
| **Executor** | [Mergiraf](https://mergiraf.org/) | "保守而不 silent resolve"的 merge driver 策略：不确定时保留 conflict markers |
| **Orchestrator** | [Agent Orchestrator](https://github.com/ComposioHQ/agent-orchestrator) | 并行 agent 调度、独立 worktree 隔离、CI 失败处理 |
| **HumanInterface** | [vit](https://github.com/LucasHJin/vit) | post-merge validation + user confirmation 的 HiTL 流程 |
| **PlannerJudge** | [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | PM/Architect 角色分工 SOP，独立角色审查规划产物 |

**合并内核推荐选型**：
- 优先评估 `weave` 的 `weave-core` 模块作为语义合并内核。
- 若 `weave` 不适配，退化为 `git merge-file`（三向合并）+ LLM 辅助语义补全。
- `Mergiraf` 可作为 merge driver 备选，其"宁可保留冲突标记也不过度乐观合并"的策略与本系统原则高度一致。
