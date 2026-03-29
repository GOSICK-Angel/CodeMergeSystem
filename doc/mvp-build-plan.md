# MVP 实现计划（新会话执行版）

> **本文档用途**：供新会话直接执行的完整实施指南。所有设计决策已在以下文档中确定，
> 实现时**必须与之保持一致，不得偏移**：
> - `doc/architecture.md` — 目录结构、技术栈
> - `doc/agents-design.md` — 6 个 Agent 职责、LLM 配置、质疑机制、无超时默认策略
> - `doc/data-models.md` — 所有 Pydantic 模型定义（权威来源）
> - `doc/flow.md` — 状态机、6 Phase 流程、Mermaid 图
> - `doc/implementation-plan.md` — 算法设计、Prompt 框架、YAML 配置模板

---

## 目录

1. [前置约束与不可违背原则](#1-前置约束与不可违背原则)
2. [项目初始化](#2-项目初始化)
3. [实施顺序与依赖关系](#3-实施顺序与依赖关系)
4. [Layer 1：数据模型层](#4-layer-1数据模型层)
5. [Layer 2：工具层](#5-layer-2工具层)
6. [Layer 3：LLM 层](#6-layer-3llm-层)
7. [Layer 4：Agent 层](#7-layer-4agent-层)
8. [Layer 5：编排层](#8-layer-5编排层)
9. [Layer 6：CLI 层](#9-layer-6cli-层)
10. [集成验证检查点](#10-集成验证检查点)
11. [文件创建清单](#11-文件创建清单)

---

## 1. 前置约束与不可违背原则

实现前必须熟知以下约束，每次写代码都要检查：

### 1.1 绝对禁止项

| 禁止行为 | 原因 | 来源文档 |
|---------|------|---------|
| 超时后以默认策略替代人工决策 | 静默误合，违反"不确定即升级"原则 | `agents-design.md §7.3` |
| Executor 私自提升/降低风险分类 | 只能通过 PlanDisputeRequest 请求修订 | `agents-design.md §2.3` |
| Judge/PlannerJudge 写入任何文件 | 审查隔离原则，ReadOnlyStateView 强制阻止 | `agents-design.md §6` |
| 跳过或忽略未解决冲突 | 必须记录到 FileDecisionRecord 或升级人工 | `flow.md §3.3` |
| 默认"目标分支优先"或"当前分支优先" | 必须按语义决策 | `architecture.md §P2` |
| `DecisionSource.TIMEOUT_DEFAULT` | 已从枚举中移除，不得使用 | `data-models.md §5` |
| Agent 构造时硬编码 API Key | 必须从 `api_key_env` 环境变量读取 | `data-models.md §1` |

### 1.2 必须实现的核心机制

- **PlannerJudge 审查循环**：最多 2 轮（`max_plan_revision_rounds`），超出升级人工
- **Plan Dispute 流程**：Executor 发起 → Planner 修订 → PlannerJudge 再审 → 继续执行
- **ReadOnlyStateView**：Judge 和 PlannerJudge 只能通过此视图访问状态
- **原子性快照**：Executor 每次写文件前必须保存 `original_snapshot`
- **检查点幂等性**：重复处理同一文件结果相同，不产生副作用

### 1.3 Agent LLM 提供商对立原则

```
Planner       → anthropic (claude-opus-4-6)
PlannerJudge  → openai    (gpt-4o)          ← 与 Planner 不同提供商
ConflictAnalyst → anthropic (claude-sonnet-4-6)
Executor      → openai    (gpt-4o)
Judge         → anthropic (claude-opus-4-6) ← 与 Executor 不同提供商
HumanInterface → anthropic (claude-haiku-4-5-20251001)
```

---

## 2. 项目初始化

### 2.1 目录结构创建

```bash
mkdir -p CodeMergeSystem/src/{agents,core,tools,models,llm/prompts,cli/commands}
mkdir -p CodeMergeSystem/tests/{unit,integration,fixtures/{sample_diffs,sample_configs}}
mkdir -p CodeMergeSystem/{config,outputs/checkpoints}
touch CodeMergeSystem/src/{agents,core,tools,models,llm,cli}/__init__.py
touch CodeMergeSystem/src/llm/prompts/__init__.py
```

### 2.2 `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "code-merge-system"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.5",
    "gitpython>=3.1",
    "unidiff>=0.7",
    "anthropic>=0.40",
    "openai>=1.50",
    "tenacity>=8.2",
    "click>=8.1",
    "rich>=13.0",
    "pyyaml>=6.0",
    "jinja2>=3.1",
]

[project.scripts]
merge = "src.cli.main:cli"

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-asyncio>=0.21",
    "pytest-mock>=3.12",
    "pytest-cov>=4.1",
    "mypy>=1.8",
    "ruff>=0.3",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.mypy]
python_version = "3.11"
strict = true
```

---

## 3. 实施顺序与依赖关系

```
Layer 1: models/          ← 无外部依赖，最先实现
    ↓
Layer 2: tools/           ← 依赖 models/
    ↓
Layer 3: llm/             ← 依赖 models/
    ↓
Layer 4: agents/          ← 依赖 models/ + tools/ + llm/
    ↓
Layer 5: core/            ← 依赖所有 agents/ + models/
    ↓
Layer 6: cli/             ← 依赖 core/
```

**每层完成后运行该层的单元测试，确保通过后再进入下一层。**

---

## 4. Layer 1：数据模型层

> 权威定义在 `doc/data-models.md`，以下为实现要点，细节以该文档为准。

### 4.1 实现顺序

```
src/models/
├── config.py          # 第1步：MergeConfig（含 AgentLLMConfig）
├── diff.py            # 第2步：FileDiff、DiffHunk、RiskLevel
├── plan.py            # 第3步：MergePlan、MergePhase
├── plan_judge.py      # 第4步：PlanJudgeVerdict（新模型）
├── dispute.py         # 第5步：PlanDisputeRequest（新模型）
├── conflict.py        # 第6步：ConflictPoint、ConflictAnalysis
├── decision.py        # 第7步：MergeDecision、FileDecisionRecord（无 TIMEOUT_DEFAULT）
├── judge.py           # 第8步：JudgeVerdict、JudgeIssue
├── human.py           # 第9步：HumanDecisionRequest
├── state.py           # 第10步：MergeState（含所有新字段）
└── message.py         # 第11步：AgentMessage（含 PLANNER_JUDGE）
```

### 4.2 `src/models/config.py` 关键实现点

```python
# 每个 Agent 独立配置，api_key_env 不可有默认密钥值
class AgentLLMConfig(BaseModel):
    provider: Literal["anthropic", "openai"]
    model: str
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(default=8192, ge=512)
    max_retries: int = Field(default=3, ge=1)
    api_key_env: str  # 必填，如 "ANTHROPIC_API_KEY"

class MergeConfig(BaseModel):
    # 注意：无 human_decision_timeout_hours 字段
    # 注意：有 max_plan_revision_rounds，默认 2
    max_plan_revision_rounds: int = Field(default=2, ge=1, le=5)
    agents: AgentsLLMConfig = Field(default_factory=AgentsLLMConfig)
    ...
```

### 4.3 `src/models/state.py` 关键实现点

```python
class SystemStatus(str, Enum):
    # 必须包含以下新状态：
    PLAN_REVIEWING = "plan_reviewing"
    PLAN_REVISING = "plan_revising"
    PLAN_DISPUTE_PENDING = "plan_dispute_pending"
    # 其余状态见 data-models.md §9

class MergeState(BaseModel):
    # 必须包含以下新字段：
    plan_judge_verdict: PlanJudgeVerdict | None = None
    plan_disputes: list[PlanDisputeRequest] = Field(default_factory=list)
    plan_revision_rounds: int = 0
    # 注意：human_decisions 中无超时默认项
```

### 4.4 `src/models/decision.py` 关键实现点

```python
class DecisionSource(str, Enum):
    AUTO_PLANNER = "auto_planner"
    AUTO_EXECUTOR = "auto_executor"
    HUMAN = "human"
    BATCH_HUMAN = "batch_human"
    # 严禁添加 TIMEOUT_DEFAULT
```

### 4.5 单元测试要求

```
tests/unit/test_models.py
- test_merge_config_no_timeout_field()      ← 验证没有 human_decision_timeout_hours
- test_agent_llm_config_requires_env_var()  ← api_key_env 不可为空
- test_decision_source_no_timeout()         ← DecisionSource 无 TIMEOUT_DEFAULT
- test_merge_state_new_fields()             ← plan_judge_verdict、plan_disputes
- test_merge_phase_includes_plan_review()   ← MergePhase 含新枚举值
- test_system_status_new_states()           ← SystemStatus 含新状态
```

---

## 5. Layer 2：工具层

### 5.1 实现顺序

```
src/tools/
├── git_tool.py          # 第1步：Git 操作封装
├── file_classifier.py   # 第2步：风险评分（含算法，见 implementation-plan.md §3.1）
├── diff_parser.py       # 第3步：Diff 解析
├── patch_applier.py     # 第4步：Patch 应用（含快照机制）
└── report_writer.py     # 第5步：报告输出
```

### 5.2 `src/tools/git_tool.py` 关键 API

```python
class GitTool:
    def __init__(self, repo_path: str): ...

    def get_merge_base(self, upstream_ref: str, fork_ref: str) -> str:
        """返回 merge-base commit hash"""

    def get_changed_files(self, base: str, head: str) -> list[tuple[str, str]]:
        """返回 (status, file_path) 列表，status: A/M/D/R"""

    def get_file_content(self, ref: str, file_path: str) -> str | None:
        """获取指定 ref 下的文件内容，文件不存在返回 None"""

    def get_three_way_diff(
        self, base: str, current: str, target: str, file_path: str
    ) -> tuple[str | None, str | None, str | None]:
        """返回 (base_content, current_content, target_content)"""

    def create_working_branch(self, branch_name: str, base_ref: str) -> str:
        """创建并切换到工作分支"""

    def apply_patch(self, patch_content: str) -> bool:
        """应用 git patch，返回是否成功"""

    def write_file_content(self, file_path: str, content: str) -> None:
        """直接写入文件内容（绕过 patch，用于 SEMANTIC_MERGE）"""

    def get_commit_messages(self, file_path: str, ref: str, limit: int = 10) -> list[str]:
        """获取文件相关的提交历史（git blame 信息）"""
```

### 5.3 `src/tools/file_classifier.py` 关键实现点

完整算法见 `doc/implementation-plan.md §3.1`，此处列出关键约束：

```python
def compute_risk_score(file_diff: FileDiff, config: FileClassifierConfig) -> float:
    # 5维加权评分：size(0.15) + conflict_density(0.35) + change_ratio(0.20)
    #              + file_type(0.20) + security(0.10)
    # 强制规则覆盖（优先级高于评分）：
    # - 匹配 always_take_target_patterns → 强制返回 0.1
    # - 匹配 security_sensitive.patterns → 强制返回 max(raw_score, 0.8)

def classify_file(risk_score: float, config: FileClassifierConfig) -> RiskLevel:
    # risk_score < 0.3  → AUTO_SAFE
    # 0.3 ≤ score < 0.6 → AUTO_RISKY
    # score ≥ 0.6       → HUMAN_REQUIRED
    # 仅删除操作        → DELETED_ONLY
    # 二进制文件        → BINARY
    # 匹配排除规则      → EXCLUDED
```

### 5.4 `src/tools/patch_applier.py` 快照机制（核心约束）

```python
async def apply_with_snapshot(
    file_path: str,
    new_content: str,
    git_tool: GitTool,
    state: MergeState,
) -> FileDecisionRecord:
    # 步骤1：读取并保存原始内容（快照）
    original = Path(file_path).read_text(encoding="utf-8") if Path(file_path).exists() else None

    try:
        # 步骤2：写入新内容
        Path(file_path).write_text(new_content, encoding="utf-8")
        # 步骤3：记录到 FileDecisionRecord（含 original_snapshot）
        ...
    except Exception as e:
        # 步骤4：失败则恢复快照，标记 ESCALATE_HUMAN
        if original is not None:
            Path(file_path).write_text(original, encoding="utf-8")
        return create_escalate_record(file_path, str(e))
```

### 5.5 单元测试要求

```
tests/unit/test_file_classifier.py
- test_security_sensitive_always_high_risk()      ← 安全路径强制 ≥ 0.8
- test_always_take_target_always_low_risk()        ← 强制低风险规则
- test_risk_score_weights_sum_to_one()            ← 权重校验

tests/unit/test_diff_parser.py
- test_parse_conflict_markers()                    ← <<< === >>> 识别
- test_three_way_diff_extraction()

tests/unit/test_patch_applier.py
- test_snapshot_saved_before_write()              ← 快照先于写入
- test_rollback_on_failure()                      ← 失败时自动恢复
```

---

## 6. Layer 3：LLM 层

### 6.1 实现顺序

```
src/llm/
├── client.py                        # 第1步：LLMClientFactory
├── prompts/
│   ├── planner_prompts.py           # 第2步
│   ├── planner_judge_prompts.py     # 第3步（新增）
│   ├── analyst_prompts.py           # 第4步
│   ├── executor_prompts.py          # 第5步
│   └── judge_prompts.py             # 第6步
└── response_parser.py               # 第7步
```

### 6.2 `src/llm/client.py` 工厂模式

```python
class LLMClient(ABC):
    """统一 LLM 客户端抽象"""
    @abstractmethod
    async def complete(self, messages: list[dict], **kwargs) -> str: ...

    @abstractmethod
    async def complete_structured(self, messages: list[dict], schema: type[BaseModel]) -> BaseModel: ...

class AnthropicClient(LLMClient):
    def __init__(self, model: str, api_key: str, temperature: float, max_tokens: int, max_retries: int): ...

class OpenAIClient(LLMClient):
    def __init__(self, model: str, api_key: str, temperature: float, max_tokens: int, max_retries: int): ...

class LLMClientFactory:
    @staticmethod
    def create(config: AgentLLMConfig) -> LLMClient:
        api_key = os.environ.get(config.api_key_env)
        if not api_key:
            raise EnvironmentError(
                f"Required env var '{config.api_key_env}' is not set. "
                f"Needed for agent using {config.provider}/{config.model}."
            )
        if config.provider == "anthropic":
            return AnthropicClient(...)
        elif config.provider == "openai":
            return OpenAIClient(...)
        raise ValueError(f"Unknown provider: {config.provider}")
```

### 6.3 Prompt 设计约束

**重要**：Planner 与 PlannerJudge 的 Prompt 必须体现不同视角：

`planner_prompts.py` — 规划者视角：
```python
PLANNER_SYSTEM = """你是代码合并规划专家。你的任务是分析两个分支的差异，
将所有变更文件分类为不同风险等级，生成阶段化合并计划。
专注于：完整覆盖所有文件、合理估计风险、识别关键依赖关系。"""

def build_classification_prompt(file_diffs: list[FileDiff], project_context: str) -> str: ...
def build_context_summary_prompt(repo_structure: str) -> str: ...
def build_revision_prompt(original_plan: MergePlan, judge_issues: list[PlanIssue]) -> str:
    """针对 PlannerJudge 指出的具体问题，重新分析受影响文件"""
    ...
```

`planner_judge_prompts.py` — 审查者视角（独立于 Planner）：
```python
PLANNER_JUDGE_SYSTEM = """你是代码合并计划的独立审查员。你的任务是发现计划中
可能被低估的风险、错误的文件分类、遗漏的安全敏感文件，以及批次粒度问题。
你不了解 Planner 的推理过程，只看最终计划和原始 diff，独立得出结论。
发现问题时，必须指出具体文件路径和具体原因，不允许模糊描述。"""

def build_plan_review_prompt(plan: MergePlan, file_diffs: list[FileDiff]) -> str: ...
def build_issue_report_prompt(issues: list[PlanIssue]) -> str: ...
```

`judge_prompts.py` — 审查者视角（独立于 Executor）：
```python
JUDGE_SYSTEM = """你是代码合并结果的独立审查员。你的任务是验证合并结果是否
保留了下游分支的所有私有逻辑，以及是否正确引入了上游分支的所有改动。
你不了解 Executor 的决策过程，只看最终合并结果和原始 diff，独立评估质量。"""
```

### 6.4 `src/llm/response_parser.py` 关键解析函数

```python
def parse_plan_judge_verdict(raw: str | dict) -> PlanJudgeVerdict:
    """解析 PlannerJudge 的审查结论"""

def parse_conflict_analysis(raw: str | dict) -> ConflictAnalysis:
    """解析 ConflictAnalyst 的分析结果，含置信度"""

def parse_judge_verdict(raw: str | dict) -> JudgeVerdict:
    """解析 Judge 的最终裁决"""

def parse_merge_result(raw: str | dict) -> str:
    """解析 Executor SEMANTIC_MERGE 的合并后文件内容"""

# 所有解析函数必须：
# 1. 处理 LLM 输出不符合预期格式的情况（raise ParseError，上层重试）
# 2. 验证置信度范围 [0.0, 1.0]
# 3. 验证枚举值合法性
```

---

## 7. Layer 4：Agent 层

### 7.1 `src/agents/base_agent.py`

```python
class BaseAgent(ABC):
    agent_type: AgentType  # 子类必须定义

    def __init__(self, llm_config: AgentLLMConfig):
        self.llm = LLMClientFactory.create(llm_config)
        self.logger = logging.getLogger(f"agent.{self.agent_type.value}")

    @abstractmethod
    async def run(self, state: MergeState | ReadOnlyStateView) -> AgentMessage:
        """主执行入口。只读 Agent 接收 ReadOnlyStateView，写 Agent 接收 MergeState。"""

    @abstractmethod
    def can_handle(self, state: MergeState) -> bool:
        """判断当前状态是否满足该 Agent 的执行前置条件"""

    async def _call_llm_with_retry(
        self,
        messages: list[dict],
        schema: type[BaseModel] | None = None,
        max_retries: int = 3,
    ) -> str | BaseModel:
        """带指数退避重试的 LLM 调用"""
```

### 7.2 `src/agents/planner_agent.py`

```python
class PlannerAgent(BaseAgent):
    agent_type = AgentType.PLANNER

    async def run(self, state: MergeState) -> AgentMessage:
        """Phase 1：分析 diff，生成 MergePlan"""

    async def revise_plan(
        self,
        state: MergeState,
        judge_issues: list[PlanIssue],
    ) -> MergePlan:
        """
        被 Orchestrator 调用，针对 PlannerJudge 指出的问题修订计划。
        只修订被质疑的具体文件，不做完整重规划。
        """

    async def handle_dispute(
        self,
        state: MergeState,
        dispute: PlanDisputeRequest,
    ) -> MergePlan:
        """
        被 Orchestrator 调用，响应 Executor 的 Plan Dispute。
        针对 dispute.disputed_files 重新分析，输出修订后的计划。
        """

    def _classify_file(self, file_diff: FileDiff, config: MergeConfig) -> RiskLevel: ...
```

### 7.3 `src/agents/planner_judge_agent.py`

```python
class PlannerJudgeAgent(BaseAgent):
    agent_type = AgentType.PLANNER_JUDGE

    async def run(self, state: ReadOnlyStateView) -> AgentMessage:
        """
        Phase 1.5：独立审查 MergePlan。
        注意：接收 ReadOnlyStateView，不得写入任何状态。
        """

    async def review_plan(
        self,
        plan: MergePlan,
        file_diffs: list[FileDiff],
        revision_round: int,
    ) -> PlanJudgeVerdict:
        """
        执行计划审查，返回 PlanJudgeVerdict。
        revision_round 用于在 Prompt 中提示这是第几次审查（首次 or 修订后复审）。
        """
```

### 7.4 `src/agents/executor_agent.py`

```python
class ExecutorAgent(BaseAgent):
    agent_type = AgentType.EXECUTOR

    async def execute_auto_merge(
        self,
        file_diff: FileDiff,
        strategy: MergeDecision,
        state: MergeState,
    ) -> FileDecisionRecord:
        """
        执行单个文件的自动合并。
        写操作前必须保存快照（patch_applier.apply_with_snapshot）。
        """

    async def execute_semantic_merge(
        self,
        file_diff: FileDiff,
        conflict_analysis: ConflictAnalysis,
        state: MergeState,
    ) -> FileDecisionRecord:
        """调用 LLM 生成语义融合内容，再写入"""

    async def execute_human_decision(
        self,
        request: HumanDecisionRequest,
        state: MergeState,
    ) -> FileDecisionRecord:
        """按人工指定策略执行，decision_source = HUMAN"""

    def raise_plan_dispute(
        self,
        file_diff: FileDiff,
        reason: str,
        suggested: dict[str, RiskLevel],
        impact: str,
        state: MergeState,
    ) -> PlanDisputeRequest:
        """
        发现计划问题时调用。
        将 PlanDisputeRequest 追加到 state.plan_disputes。
        不修改 file_diff.risk_level（只能通过正式质疑流程修改）。
        """
```

### 7.5 `src/agents/judge_agent.py`

```python
class JudgeAgent(BaseAgent):
    agent_type = AgentType.JUDGE

    async def run(self, state: ReadOnlyStateView) -> AgentMessage:
        """Phase 5：只读审查合并结果，不修改任何文件。"""

    async def review_file(
        self,
        file_path: str,
        merged_content: str,
        decision_record: FileDecisionRecord,
        original_diff: FileDiff,
    ) -> list[JudgeIssue]:
        """
        对单个高风险文件的深度审查。
        使用独立于 Executor 的 Prompt 模板和视角。
        必须检查：
        - 无遗留冲突标记（<<<<<<、>>>>>>、======）
        - 下游私有逻辑是否保留
        - 上游关键功能是否引入
        """

    def compute_verdict(self, all_issues: list[JudgeIssue]) -> VerdictType:
        """
        PASS：无 CRITICAL/HIGH 问题
        CONDITIONAL：有 MEDIUM/LOW 问题
        FAIL：有 CRITICAL/HIGH 问题
        """
```

### 7.6 `src/agents/human_interface_agent.py`

```python
class HumanInterfaceAgent(BaseAgent):
    agent_type = AgentType.HUMAN_INTERFACE

    async def generate_report(
        self,
        requests: list[HumanDecisionRequest],
        output_path: str,
    ) -> str:
        """生成 Markdown 格式的人工决策报告"""

    async def collect_decisions_cli(
        self,
        requests: list[HumanDecisionRequest],
    ) -> list[HumanDecisionRequest]:
        """
        CLI 交互模式：逐项引导用户输入决策。
        系统永远不会以默认策略替代用户未填写的项。
        若用户跳过，该项状态仍为 ESCALATE_HUMAN，等待下次 resume 时处理。
        """

    async def collect_decisions_file(
        self,
        yaml_path: str,
        requests: list[HumanDecisionRequest],
    ) -> list[HumanDecisionRequest]:
        """文件批注模式：读取用户编辑的 YAML 文件"""

    def validate_decision(self, request: HumanDecisionRequest) -> bool:
        """
        验证人工决策合法性：
        - human_decision 必须是合法的 MergeDecision 枚举值
        - MANUAL_PATCH 时 custom_content 不能为空
        - 不接受 ESCALATE_HUMAN 作为人工决策（会造成死循环）
        """
```

### 7.7 Agent 层单元测试要求

```
tests/unit/test_agents.py

# PlannerJudge 审查隔离
- test_planner_judge_receives_readonly_view()        ← 确认接收 ReadOnlyStateView
- test_planner_judge_cannot_write_state()           ← ReadOnlyStateView 写入抛出异常
- test_judge_cannot_write_state()                   ← 同上

# Executor 质疑机制
- test_executor_dispute_does_not_change_risk_level() ← 只生成 request，不修改分类
- test_executor_requires_snapshot_before_write()    ← 快照机制验证

# HumanInterface 无默认策略
- test_human_interface_never_auto_decides()          ← 跳过的项保持 ESCALATE_HUMAN
- test_validate_decision_rejects_escalate_human()   ← ESCALATE_HUMAN 不可作为决策

# PlannerJudge 修订轮次
- test_plan_revision_stops_at_max_rounds()          ← 超出 max_plan_revision_rounds 升级人工
```

---

## 8. Layer 5：编排层

### 8.1 `src/core/state_machine.py`

```python
# 完整状态转换表，必须与 doc/flow.md §1.2 严格一致
VALID_TRANSITIONS: dict[SystemStatus, list[SystemStatus]] = {
    SystemStatus.INITIALIZED: [SystemStatus.PLANNING, SystemStatus.FAILED],
    SystemStatus.PLANNING: [SystemStatus.PLAN_REVIEWING, SystemStatus.FAILED],
    SystemStatus.PLAN_REVIEWING: [
        SystemStatus.AUTO_MERGING,          # APPROVED
        SystemStatus.PLAN_REVISING,         # REVISION_NEEDED（rounds < max）
        SystemStatus.AWAITING_HUMAN,        # REVISION_NEEDED（rounds == max）
        SystemStatus.PLANNING,              # CRITICAL_REPLAN
        SystemStatus.FAILED,
    ],
    SystemStatus.PLAN_REVISING: [SystemStatus.PLAN_REVIEWING, SystemStatus.FAILED],
    SystemStatus.AUTO_MERGING: [
        SystemStatus.ANALYZING_CONFLICTS,
        SystemStatus.JUDGE_REVIEWING,       # 无高风险文件时跳过 Phase 3/4
        SystemStatus.PLAN_DISPUTE_PENDING,
        SystemStatus.FAILED,
        SystemStatus.PAUSED,
    ],
    SystemStatus.PLAN_DISPUTE_PENDING: [
        SystemStatus.PLAN_REVISING,         # Planner 开始修订
        SystemStatus.AWAITING_HUMAN,        # Planner 无法解决，升级人工
    ],
    SystemStatus.ANALYZING_CONFLICTS: [
        SystemStatus.AWAITING_HUMAN,
        SystemStatus.JUDGE_REVIEWING,
        SystemStatus.PLAN_DISPUTE_PENDING,
        SystemStatus.FAILED,
    ],
    SystemStatus.AWAITING_HUMAN: [
        SystemStatus.ANALYZING_CONFLICTS,
        SystemStatus.JUDGE_REVIEWING,
        SystemStatus.FAILED,
        # 注意：无超时自动转换，只有用户明确操作才转换
    ],
    SystemStatus.JUDGE_REVIEWING: [
        SystemStatus.GENERATING_REPORT,
        SystemStatus.AWAITING_HUMAN,        # CONDITIONAL
        SystemStatus.ANALYZING_CONFLICTS,   # FAIL + analysis_needed
        SystemStatus.FAILED,
    ],
    SystemStatus.GENERATING_REPORT: [SystemStatus.COMPLETED, SystemStatus.FAILED],
    SystemStatus.PAUSED: [...],  # 恢复到暂停前状态
    # COMPLETED / FAILED 为终态
}

class StateMachine:
    def transition(self, state: MergeState, target: SystemStatus, reason: str) -> None:
        """
        执行状态转换。必须验证转换合法性。
        记录转换历史（时间戳 + 原因）到 state.messages。
        """

    def can_transition(self, current: SystemStatus, target: SystemStatus) -> bool: ...
```

### 8.2 `src/core/orchestrator.py`

核心编排逻辑，按 Phase 顺序调度 Agent：

```python
class Orchestrator:
    def __init__(self, config: MergeConfig):
        self.config = config
        # 按 AgentsLLMConfig 构造各 Agent
        self.planner = PlannerAgent(config.agents.planner)
        self.planner_judge = PlannerJudgeAgent(config.agents.planner_judge)
        self.conflict_analyst = ConflictAnalystAgent(config.agents.conflict_analyst)
        self.executor = ExecutorAgent(config.agents.executor)
        self.judge = JudgeAgent(config.agents.judge)
        self.human_interface = HumanInterfaceAgent(config.agents.human_interface)
        self.state_machine = StateMachine()
        self.checkpoint = Checkpoint(config.output.directory)

    async def run(self, state: MergeState) -> MergeState:
        """主执行循环，按 Phase 顺序推进"""

    async def _run_phase1(self, state: MergeState) -> None:
        """Planner 分析 diff，生成 MergePlan"""

    async def _run_phase1_5(self, state: MergeState) -> None:
        """
        PlannerJudge 审查计划。
        - 传入 ReadOnlyStateView（不是 state）
        - 循环审查，直到 APPROVED 或超出 max_plan_revision_rounds
        - 超出后进入 AWAITING_HUMAN（不是 FAILED）
        """
        readonly = ReadOnlyStateView(state)
        for round_num in range(self.config.max_plan_revision_rounds + 1):
            verdict = await self.planner_judge.review_plan(
                state.merge_plan, state.file_diffs, round_num
            )
            # 由 Orchestrator 代理写入（PlannerJudge 自身不写）
            state.plan_judge_verdict = verdict
            state.plan_revision_rounds = round_num

            if verdict.result == PlanJudgeResult.APPROVED:
                self.state_machine.transition(state, SystemStatus.AUTO_MERGING, "plan approved")
                return
            elif verdict.result == PlanJudgeResult.CRITICAL_REPLAN:
                self.state_machine.transition(state, SystemStatus.PLANNING, "critical replan")
                return
            elif round_num < self.config.max_plan_revision_rounds:
                # 请 Planner 修订
                self.state_machine.transition(state, SystemStatus.PLAN_REVISING, ...)
                revised_plan = await self.planner.revise_plan(state, verdict.issues)
                state.merge_plan = revised_plan  # Orchestrator 代理写入
            else:
                # 超出轮次，升级人工
                self.state_machine.transition(state, SystemStatus.AWAITING_HUMAN,
                    "plan review exceeded max revision rounds")
                return

    async def _handle_plan_dispute(self, state: MergeState, dispute: PlanDisputeRequest) -> None:
        """
        处理 Executor 的计划质疑：
        1. 暂停受影响文件
        2. 触发 Planner 修订
        3. PlannerJudge 再次审查修订结果
        4. 审查通过后标记 dispute.resolved = True
        """

    async def _run_phase5(self, state: MergeState) -> None:
        """
        Judge 审查。传入 ReadOnlyStateView，
        Judge 的审查结论由 Orchestrator 代理写入 state.judge_verdict。
        """
        readonly = ReadOnlyStateView(state)
        verdict = await self.judge.run(readonly)
        state.judge_verdict = verdict.payload["verdict"]  # 代理写入
```

### 8.3 `src/core/checkpoint.py`

```python
class Checkpoint:
    def save(self, state: MergeState, tag: str) -> Path:
        """
        保存检查点到 outputs/checkpoints/run_{run_id}_{tag}.json。
        同时更新软链接 run_{run_id}_latest.json。
        序列化 MergeState 全量（含 plan_disputes、plan_judge_verdict 等新字段）。
        """

    def load(self, checkpoint_path: Path) -> MergeState:
        """从检查点文件恢复 MergeState"""

    def list_checkpoints(self, run_id: str) -> list[Path]:
        """列出指定 run_id 的所有检查点，按时间排序"""
```

保存时机（必须实现）：
- 每个 Phase 完成后
- Phase 2 每批 10 个文件后
- Phase 3 每个文件处理完后
- 进入 `AWAITING_HUMAN` 状态时
- 收到 SIGINT/SIGTERM 信号时

### 8.4 `src/core/read_only_state_view.py`

```python
class ReadOnlyStateView:
    """
    Judge 和 PlannerJudge 专用的只读状态视图。
    所有写操作在运行时抛出 PermissionError。
    返回可变对象时自动深拷贝，防止通过引用修改原始状态。
    """
    def __init__(self, state: MergeState):
        object.__setattr__(self, '_state', state)

    def __getattr__(self, name: str):
        value = getattr(self._state, name)
        if isinstance(value, (dict, list, BaseModel)):
            return deepcopy(value)
        return value

    def __setattr__(self, name: str, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            raise PermissionError(
                f"Read-only view: attempted write to '{name}'. "
                f"Use Orchestrator to write state on behalf of review agents."
            )
```

---

## 9. Layer 6：CLI 层

### 9.1 `src/cli/main.py`

```python
@click.group()
def cli(): ...

@cli.command("run")
@click.option("--config", "-c", required=True, type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="仅分析，不执行合并")
def run_command(config: str, dry_run: bool):
    """执行完整合并流程"""

@cli.command("resume")
@click.option("--run-id", required=False)
@click.option("--checkpoint", required=False, type=click.Path(exists=True))
def resume_command(run_id: str | None, checkpoint: str | None):
    """从检查点恢复执行"""

@cli.command("report")
@click.option("--run-id", required=True)
@click.option("--output", "-o", default="./outputs")
def report_command(run_id: str, output: str):
    """仅生成报告（不执行合并）"""

@cli.command("validate")
@click.option("--config", "-c", required=True, type=click.Path(exists=True))
def validate_command(config: str):
    """验证配置文件，并检查所需环境变量"""
```

### 9.2 `merge validate` 必须检查

```python
# 在 validate_command 中执行：
def validate_config_and_env(config: MergeConfig) -> list[str]:
    errors = []
    # 检查所有 AgentLLMConfig.api_key_env 对应的环境变量是否已设置
    for agent_name, agent_config in config.agents.model_dump().items():
        env_var = agent_config["api_key_env"]
        if not os.environ.get(env_var):
            errors.append(f"Agent '{agent_name}' requires env var '{env_var}' (not set)")
    # 检查 repo_path 是否是有效 git 仓库
    # 检查 upstream_ref 和 fork_ref 是否存在
    return errors
```

---

## 10. 集成验证检查点

完成所有 Layer 后，按以下顺序执行集成验证：

### 检查点 A：模型层完整性
```bash
python -c "from src.models import MergeState, MergeConfig, PlanJudgeVerdict, PlanDisputeRequest; print('OK')"
# 验证：无 TIMEOUT_DEFAULT，有 PLANNER_JUDGE，有新状态枚举
```

### 检查点 B：ReadOnlyStateView 隔离
```python
# tests/unit/test_read_only_state.py
state = MergeState(config=...)
view = ReadOnlyStateView(state)
assert view.merge_plan == state.merge_plan  # 可读
with pytest.raises(PermissionError):
    view.merge_plan = None  # 写入抛出异常
```

### 检查点 C：LLM 工厂不泄露密钥
```python
# 未设置环境变量时抛出 EnvironmentError
config = AgentLLMConfig(provider="anthropic", model="...", api_key_env="NONEXISTENT_VAR")
with pytest.raises(EnvironmentError, match="NONEXISTENT_VAR"):
    LLMClientFactory.create(config)
```

### 检查点 D：Plan Dispute 不修改分类
```python
executor = ExecutorAgent(llm_config)
state = create_test_state()
original_risk = state.file_classifications["auth/login.py"]
dispute = executor.raise_plan_dispute(
    file_diff=..., reason="...", suggested={"auth/login.py": RiskLevel.HUMAN_REQUIRED}, ...
)
assert state.file_classifications["auth/login.py"] == original_risk  # 未被修改
assert len(state.plan_disputes) == 1
```

### 检查点 E：Phase 1.5 轮次控制
```python
# 模拟 PlannerJudge 持续返回 REVISION_NEEDED，验证轮次上限
config.max_plan_revision_rounds = 2
# 第3次仍返回 REVISION_NEEDED → 转入 AWAITING_HUMAN，不是 FAILED
assert state.status == SystemStatus.AWAITING_HUMAN
```

### 检查点 F：HumanInterface 不自动决策
```python
# 模拟用户跳过所有决策
requests = [create_escalate_request(...) for _ in range(5)]
decisions = await human_interface.collect_decisions_cli(requests)
# 跳过的项状态仍为 ESCALATE_HUMAN，不被填充默认值
skipped = [r for r in decisions if r.human_decision is None]
assert len(skipped) == 5
```

### 检查点 G：端到端 Demo（使用测试 Git 仓库）
```bash
# 创建测试仓库
python tests/fixtures/create_test_repo.py --output /tmp/test-merge-repo

# 运行完整流程（使用 Mock LLM）
merge run --config tests/fixtures/sample_configs/test_config.yaml

# 验证输出
ls outputs/
# 应包含：merge_plan.json, human_report.md, judge_report.json, final_summary.md
```

---

## 11. 文件创建清单

按实施顺序排列，✅ 表示优先级 P0（MVP 必须），🔲 表示 P1（后续迭代）：

### Layer 1：数据模型层（全部 P0）
- ✅ `src/models/__init__.py`
- ✅ `src/models/config.py` — MergeConfig、AgentLLMConfig、AgentsLLMConfig
- ✅ `src/models/diff.py` — FileDiff、DiffHunk、RiskLevel、FileStatus
- ✅ `src/models/plan.py` — MergePlan、MergePhase、PhaseFileBatch
- ✅ `src/models/plan_judge.py` — PlanJudgeVerdict、PlanIssue、PlanJudgeResult
- ✅ `src/models/dispute.py` — PlanDisputeRequest
- ✅ `src/models/conflict.py` — ConflictPoint、ConflictAnalysis、ConflictType
- ✅ `src/models/decision.py` — MergeDecision、FileDecisionRecord、DecisionSource
- ✅ `src/models/judge.py` — JudgeVerdict、JudgeIssue、VerdictType
- ✅ `src/models/human.py` — HumanDecisionRequest、DecisionOption
- ✅ `src/models/state.py` — MergeState、SystemStatus
- ✅ `src/models/message.py` — AgentMessage、AgentType、MessageType

### Layer 2：工具层（全部 P0）
- ✅ `src/tools/__init__.py`
- ✅ `src/tools/git_tool.py`
- ✅ `src/tools/file_classifier.py` — 含完整风险评分算法
- ✅ `src/tools/diff_parser.py`
- ✅ `src/tools/patch_applier.py` — 含快照机制
- ✅ `src/tools/report_writer.py`

### Layer 3：LLM 层（全部 P0）
- ✅ `src/llm/__init__.py`
- ✅ `src/llm/client.py` — LLMClientFactory、AnthropicClient、OpenAIClient
- ✅ `src/llm/prompts/__init__.py`
- ✅ `src/llm/prompts/planner_prompts.py`
- ✅ `src/llm/prompts/planner_judge_prompts.py`
- ✅ `src/llm/prompts/analyst_prompts.py`
- ✅ `src/llm/prompts/executor_prompts.py`
- ✅ `src/llm/prompts/judge_prompts.py`
- ✅ `src/llm/response_parser.py`

### Layer 4：Agent 层（全部 P0）
- ✅ `src/agents/__init__.py`
- ✅ `src/agents/base_agent.py`
- ✅ `src/agents/planner_agent.py`
- ✅ `src/agents/planner_judge_agent.py`
- ✅ `src/agents/conflict_analyst_agent.py`
- ✅ `src/agents/executor_agent.py`
- ✅ `src/agents/judge_agent.py`
- ✅ `src/agents/human_interface_agent.py`

### Layer 5：编排层（全部 P0）
- ✅ `src/core/__init__.py`
- ✅ `src/core/read_only_state_view.py`
- ✅ `src/core/state_machine.py`
- ✅ `src/core/message_bus.py`
- ✅ `src/core/checkpoint.py`
- ✅ `src/core/phase_runner.py`
- ✅ `src/core/orchestrator.py`

### Layer 6：CLI 层（全部 P0）
- ✅ `src/cli/__init__.py`
- ✅ `src/cli/main.py`
- ✅ `src/cli/commands/run.py`
- ✅ `src/cli/commands/resume.py`
- ✅ `src/cli/commands/report.py`
- ✅ `src/cli/commands/validate.py`
- ✅ `src/cli/display.py`

### 配置与工程文件
- ✅ `pyproject.toml`
- ✅ `config/merge_config.example.yaml`
- ✅ `config/default_thresholds.yaml`
- 🔲 `Makefile`

### 测试文件（P0 核心用例）
- ✅ `tests/conftest.py`
- ✅ `tests/unit/test_models.py`
- ✅ `tests/unit/test_file_classifier.py`
- ✅ `tests/unit/test_diff_parser.py`
- ✅ `tests/unit/test_patch_applier.py`
- ✅ `tests/unit/test_read_only_state.py`
- ✅ `tests/unit/test_state_machine.py`
- ✅ `tests/unit/test_agents.py`
- ✅ `tests/fixtures/create_test_repo.py`
- ✅ `tests/fixtures/sample_configs/test_config.yaml`
- 🔲 `tests/integration/test_orchestrator.py`

---

## 附录：关键设计决策备忘

| 决策 | 方案 | 不可更改原因 |
|------|------|-------------|
| 人工决策无超时默认 | 跳过项保持 ESCALATE_HUMAN | 静默误合风险高于等待成本 |
| PlannerJudge 与 Planner 不同提供商 | openai vs anthropic | 同源盲区问题 |
| Judge 与 Executor 不同提供商 | anthropic vs openai | 同上 |
| Executor 不能自改风险分类 | 只能提交 PlanDisputeRequest | 审查隔离原则 |
| 写操作前必须快照 | `apply_with_snapshot` | 文件级回滚必须条件 |
| Judge 接收 ReadOnlyStateView | 运行时强制只读 | 审查结论可信度 |
| API Key 不硬编码 | api_key_env 环境变量 | 安全规范 |
