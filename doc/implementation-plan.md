# 实现计划文档

## 目录

1. [MVP 实现范围](#1-mvp-实现范围)
2. [核心代码模块清单](#2-核心代码模块清单)
3. [关键算法设计](#3-关键算法设计)
4. [LLM 调用设计](#4-llm-调用设计)
5. [配置文件示例](#5-配置文件示例)
6. [示例输出文档模板](#6-示例输出文档模板)
7. [运行方式说明](#7-运行方式说明)
8. [后续可增强方向](#8-后续可增强方向)

---

## 1. MVP 实现范围

### 1.1 MVP 必须实现（P0）

| 功能模块 | 说明 |
|----------|------|
| 配置加载与验证 | 从 YAML 加载 `MergeConfig`（含各 Agent LLM 配置），Pydantic 验证 |
| Git diff 解析 | 获取全量文件变更，解析 unified diff |
| 文件风险评分 | 基于规则的评分（不依赖 LLM） |
| Phase 1 完整流程 | Planner 分析 diff，生成 MergePlan |
| **Phase 1.5 完整流程** | **PlannerJudge 独立审查计划，支持最多 2 轮修订** |
| Phase 2 完整流程 | Executor AUTO_SAFE 处理，含 Plan Dispute 触发逻辑 |
| Phase 3 完整流程 | ConflictAnalyst + Executor 高风险处理 |
| Phase 4 CLI 交互模式 | HumanInterface 终端交互收集决策（无超时默认策略） |
| Phase 5 Judge 审查 | 基于 LLM 的合并结果审查 |
| Phase 6 报告生成 | JSON + Markdown 双格式报告 |
| 断点续传 | 检查点保存与恢复 |
| 文件级回滚 | 快照保存与恢复 |
| CLI 入口 | `merge run` / `merge resume` / `merge report` |

### 1.2 增强功能（P1，MVP 后迭代）

| 功能模块 | 说明 | 依赖条件 |
|----------|------|----------|
| 文件批注模式（HumanInterface） | 生成可批注 YAML，`resume` 读取 | P0 完成 |
| LLM 辅助风险评分 | 结合代码语义提升评分准确度 | P0 完成 |
| 相似冲突批量决策 | 识别同类冲突，一键批量处理 | P0 完成 |
| 静态语法检查集成 | Phase 5 对 Python/JS/TS 文件做语法验证 | 可选工具依赖 |
| Web UI（HumanInterface） | 替换 CLI 交互为 Web 表单 | 额外开发成本 |
| GitHub PR 集成 | 将 HumanReport 发布为 PR Review Comments | GitHub API 权限 |
| CI/CD 集成支持 | 标准退出码、JSON 报告供 CI 读取 | P0 完成 |

### 1.3 范围外（Out of Scope）

- 自动代码质量修复（如格式化、lint 修复）
- 自动测试运行与修复
- 多仓库合并
- 非 Git 版本控制系统支持

---

## 2. 核心代码模块清单

### 2.1 `src/models/` — 数据模型层

| 文件 | 职责 | 关键类 |
|------|------|--------|
| `config.py` | 系统输入配置 | `MergeConfig`, `AgentLLMConfig`, `AgentsLLMConfig`, `ThresholdConfig` |
| `diff.py` | 文件差异描述 | `FileDiff`, `DiffHunk`, `RiskLevel`, `FileStatus` |
| `decision.py` | 合并决策记录 | `MergeDecision`, `FileDecisionRecord`, `DecisionSource` |
| `plan.py` | 合并计划 | `MergePlan`, `PhaseFileBatch`, `RiskSummary` |
| `plan_judge.py` | **计划审查结论** | **`PlanJudgeVerdict`, `PlanIssue`, `PlanJudgeResult`** |
| `dispute.py` | **Executor 计划质疑** | **`PlanDisputeRequest`** |
| `conflict.py` | 冲突分析结果 | `ConflictPoint`, `ConflictAnalysis`, `ConflictType` |
| `judge.py` | 审查裁决 | `JudgeVerdict`, `JudgeIssue`, `VerdictType` |
| `human.py` | 人工决策请求 | `HumanDecisionRequest`, `DecisionOption` |
| `state.py` | 全局状态机 | `MergeState`, `SystemStatus`, `MergePhase` |
| `message.py` | Agent 消息 | `AgentMessage`, `AgentType`, `MessageType` |

### 2.2 `src/tools/` — 工具层

| 文件 | 关键函数 | 说明 |
|------|----------|------|
| `git_tool.py` | `get_file_list_diff()`, `get_three_way_diff()`, `apply_patch()`, `create_working_branch()` | 封装所有 git 操作 |
| `file_classifier.py` | `classify_file()`, `compute_risk_score()`, `is_security_sensitive()` | 文件风险分类器 |
| `diff_parser.py` | `parse_unified_diff()`, `extract_conflict_hunks()`, `build_file_diff()` | Diff 结构化解析 |
| `patch_applier.py` | `generate_patch()`, `apply_patch_atomic()`, `verify_patch_result()` | Patch 生成与应用 |
| `report_writer.py` | `write_merge_plan()`, `write_human_report()`, `write_judge_report()`, `write_final_summary()` | 报告序列化 |

### 2.3 `src/agents/` — Agent 层

| 文件 | 关键方法 | LLM 使用 |
|------|----------|----------|
| `base_agent.py` | `run()`, `can_handle()`, `_call_llm()` | 抽象基类；构造时注入 `AgentLLMConfig` |
| `planner_agent.py` | `analyze_repository()`, `classify_all_files()`, `generate_plan()`, `revise_plan()` | 生成项目背景摘要；`revise_plan()` 处理 PlannerJudge 修订意见 |
| `planner_judge_agent.py` | `review_plan()`, `check_risk_classification()`, `check_security_coverage()` | 每次审查一次 LLM 调用；与 Planner 使用不同提供商 |
| `conflict_analyst_agent.py` | `analyze_file()`, `analyze_conflict_point()`, `compute_confidence()` | 每个冲突点一次 LLM 调用 |
| `executor_agent.py` | `execute_auto_merge()`, `execute_semantic_merge()`, `execute_human_decision()`, `raise_plan_dispute()` | SEMANTIC_MERGE 时调用；`raise_plan_dispute()` 生成 PlanDisputeRequest |
| `judge_agent.py` | `review_all_files()`, `review_file()`, `compute_verdict()` | 每个高风险文件一次 LLM 调用；与 Executor 使用不同提供商 |
| `human_interface_agent.py` | `generate_report()`, `collect_decisions_cli()`, `collect_decisions_file()`, `validate_decision()` | 低频（报告优化） |

### 2.4 `src/core/` — 编排层

| 文件 | 关键方法 | 说明 |
|------|----------|------|
| `orchestrator.py` | `run()`, `run_phase()`, `handle_phase_result()` | 主编排器 |
| `state_machine.py` | `transition()`, `can_transition()`, `record_transition()` | 状态转换管理 |
| `message_bus.py` | `publish()`, `subscribe()`, `get_messages()` | 内存消息队列 |
| `checkpoint.py` | `save()`, `load()`, `list_checkpoints()`, `get_latest()` | 检查点持久化 |
| `phase_runner.py` | `run_sequential()`, `run_parallel()`, `run_batched()` | Phase 内任务执行 |

### 2.5 `src/llm/` — LLM 层

| 文件 | 关键方法 | 说明 |
|------|----------|------|
| `client.py` | `LLMClientFactory.create(config: AgentLLMConfig)` | 按 Agent 配置创建独立客户端（Anthropic/OpenAI） |
| `prompts/planner_prompts.py` | `build_classification_prompt()`, `build_context_summary_prompt()`, `build_revision_prompt()` | Planner 专用模板（含修订场景） |
| `prompts/planner_judge_prompts.py` | `build_plan_review_prompt()`, `build_issue_report_prompt()` | **PlannerJudge 专用模板，视角独立于 Planner** |
| `prompts/analyst_prompts.py` | `build_conflict_analysis_prompt()`, `build_merge_suggestion_prompt()` | ConflictAnalyst 模板 |
| `prompts/judge_prompts.py` | `build_review_prompt()`, `build_verdict_prompt()` | Judge 模板（视角独立于 Executor） |
| `prompts/executor_prompts.py` | `build_semantic_merge_prompt()`, `build_dispute_prompt()` | Executor 模板（含质疑场景） |
| `response_parser.py` | `parse_conflict_analysis()`, `parse_plan_judge_verdict()`, `parse_judge_verdict()`, `parse_merge_result()` | LLM 响应解析 |

---

## 3. 关键算法设计

### 3.1 文件风险评分算法

**输入**：`FileDiff` 对象、文件路径、配置规则

**输出**：`risk_score: float`（0.0 ~ 1.0）

```python
def compute_risk_score(file_diff: FileDiff, config: FileClassifierConfig) -> float:
    weights = {
        "size": 0.15,
        "conflict_density": 0.35,
        "change_ratio": 0.20,
        "file_type": 0.20,
        "security": 0.10,
    }

    # 1. 大小分：文件变更行数越多，风险越高
    size_score = min(1.0, (file_diff.lines_changed / 500) ** 0.5)

    # 2. 冲突密度分：冲突区域占总变更行数的比例
    total_lines = max(1, file_diff.lines_added + file_diff.lines_deleted)
    conflict_lines = sum(h.end_line_current - h.start_line_current
                         for h in file_diff.hunks if h.has_conflict)
    conflict_density_score = min(1.0, conflict_lines / total_lines)

    # 3. 变更比例分：相对于文件总行数的变更比例
    change_ratio = file_diff.lines_changed / max(1, estimate_total_lines(file_diff))
    change_ratio_score = min(1.0, change_ratio * 2)

    # 4. 文件类型分
    type_score_map = {
        ".py": 0.7, ".ts": 0.7, ".js": 0.6,
        ".java": 0.7, ".go": 0.7, ".rs": 0.8,
        ".yaml": 0.5, ".json": 0.4, ".toml": 0.4,
        ".md": 0.1, ".txt": 0.1,
        ".sql": 0.8, ".sh": 0.7,
    }
    ext = Path(file_diff.file_path).suffix.lower()
    type_score = type_score_map.get(ext, 0.5)

    # 5. 安全敏感分
    security_score = 1.0 if file_diff.is_security_sensitive else 0.0

    raw_score = (
        weights["size"] * size_score +
        weights["conflict_density"] * conflict_density_score +
        weights["change_ratio"] * change_ratio_score +
        weights["file_type"] * type_score +
        weights["security"] * security_score
    )

    # 应用强制规则覆盖
    if matches_any_pattern(file_diff.file_path, config.always_take_target_patterns):
        return 0.1  # 强制低风险
    if matches_any_pattern(file_diff.file_path, config.security_sensitive.patterns):
        return max(raw_score, 0.8)  # 强制高风险

    return round(raw_score, 3)
```

### 3.2 冲突置信度评分算法

**输入**：LLM 对冲突的分析结果（结构化 JSON）

**输出**：`confidence: float`（0.0 ~ 1.0）

```python
def compute_conflict_confidence(
    llm_analysis: dict,
    conflict_type: ConflictType,
    has_base_version: bool
) -> float:
    base_confidence = llm_analysis.get("raw_confidence", 0.5)

    # 1. 冲突类型调整因子
    type_adjustment = {
        ConflictType.SEMANTIC_EQUIVALENT: +0.20,  # 语义等价最容易处理
        ConflictType.DEPENDENCY_UPDATE: +0.15,    # 依赖更新有明确规则
        ConflictType.CONFIGURATION: +0.10,        # 配置冲突通常可识别
        ConflictType.CONCURRENT_MODIFICATION: 0,  # 中性
        ConflictType.REFACTOR_VS_FEATURE: -0.10,  # 需要更多上下文
        ConflictType.DELETION_VS_MODIFICATION: -0.15,  # 删除风险高
        ConflictType.INTERFACE_CHANGE: -0.20,     # 接口变更影响广
        ConflictType.LOGIC_CONTRADICTION: -0.30,  # 逻辑矛盾最难处理
        ConflictType.UNKNOWN: -0.25,              # 未知类型不确定
    }

    # 2. 三向 diff 可用性加成
    base_bonus = 0.10 if has_base_version else 0.0

    # 3. LLM 自报置信度的可靠性修正（LLM 倾向于过度自信）
    calibrated = base_confidence * 0.85

    final_confidence = calibrated + type_adjustment.get(conflict_type, 0) + base_bonus

    # 归一化到 [0.1, 0.95]
    return max(0.10, min(0.95, round(final_confidence, 3)))
```

### 3.3 语义合并策略选择逻辑

**输入**：`ConflictAnalysis` 对象、配置阈值

**输出**：最终执行的 `MergeDecision`

```python
def select_merge_strategy(
    analysis: ConflictAnalysis,
    thresholds: ThresholdConfig
) -> MergeDecision:

    # 规则 1：置信度过低，直接升级人工
    if analysis.confidence < thresholds.human_escalation:
        return MergeDecision.ESCALATE_HUMAN

    # 规则 2：逻辑矛盾，无法自动合并
    if analysis.conflict_type == ConflictType.LOGIC_CONTRADICTION:
        if analysis.confidence < 0.90:  # 极高置信度才允许自动处理
            return MergeDecision.ESCALATE_HUMAN

    # 规则 3：语义等价，可以直接采用目标版本
    if analysis.conflict_type == ConflictType.SEMANTIC_EQUIVALENT:
        if analysis.confidence >= thresholds.auto_merge_confidence:
            return MergeDecision.TAKE_TARGET

    # 规则 4：双方修改可以共存
    if analysis.can_coexist and analysis.confidence >= thresholds.auto_merge_confidence:
        return MergeDecision.SEMANTIC_MERGE

    # 规则 5：安全敏感文件永远需要人工
    if analysis.is_security_sensitive:
        return MergeDecision.ESCALATE_HUMAN

    # 规则 6：置信度在阈值范围内，按 LLM 建议执行
    if analysis.confidence >= thresholds.auto_merge_confidence:
        return analysis.recommended_strategy

    # 默认：升级人工
    return MergeDecision.ESCALATE_HUMAN
```

---

## 4. LLM 调用设计

### 4.1 统一 LLM 客户端

所有 Agent 通过统一客户端调用 LLM，客户端负责重试、限流和响应解析：

```python
class LLMClient:
    async def complete_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> BaseModel:
        """调用 LLM 并返回结构化 Pydantic 对象"""
        ...
```

### 4.2 Planner Agent 的 LLM 调用

**用途**：生成项目背景摘要，辅助后续 Agent 理解代码上下文

**Prompt 框架**：

```python
CONTEXT_SUMMARY_PROMPT = """
你是一个资深代码审查专家。

以下是一个软件项目中的部分关键文件内容摘要，以及两个分支之间的变更统计。
请基于这些信息，用 300 字以内概括：
1. 这个项目的主要功能和技术栈
2. 下游分支（fork）相对于上游的主要定制化方向
3. 合并时需要特别注意的模块或技术点

---
项目文件摘要：
{file_summary}

---
变更统计：
- 总变更文件数：{total_files}
- 主要变更目录：{top_directories}
- 最高风险文件（Top 5）：{top_risk_files}

请用中文回答。
"""
```

### 4.3 ConflictAnalyst Agent 的 LLM 调用

**用途**：对每个冲突点进行语义分析，生成合并建议

**Prompt 框架**：

```python
CONFLICT_ANALYSIS_PROMPT = """
你是一个专业的代码合并专家，正在分析一个 Git 合并冲突。

# 项目背景
{project_context}

# 文件信息
文件路径：{file_path}
编程语言：{language}

# 三向 Diff
## 共同祖先版本（merge-base）
```{language}
{base_content}```

## 当前版本（下游 fork 的修改）
```{language}
{current_content}```

## 目标版本（上游 upstream 的修改）
```{language}
{target_content}```

# 分析任务
请分析这个冲突，输出以下结构化信息：
1. conflict_type：冲突类型（从给定枚举中选择）
2. upstream_intent：上游修改的意图（类型 + 描述 + 置信度）
3. fork_intent：下游修改的意图（类型 + 描述 + 置信度）
4. can_coexist：两个修改是否可以在逻辑上共存（true/false）
5. suggested_decision：推荐的合并策略（枚举值）
6. confidence：你对这个建议的置信度（0.0-1.0）
7. rationale：推理说明（2-4 句话）
8. risk_factors：风险因素列表

注意：
- 置信度低于 0.7 时请建议 ESCALATE_HUMAN
- 涉及安全、认证、加密的代码请建议 ESCALATE_HUMAN
- 保守原则：不确定时选择更保守的策略
"""
```

### 4.4 Judge Agent 的 LLM 调用

**用途**：独立审查合并结果，避免与 ConflictAnalyst 相同的视角偏差

**Prompt 框架**：

```python
JUDGE_REVIEW_PROMPT = """
你是一个独立的代码审查员（Code Reviewer），与最初进行冲突分析的 AI 是相互独立的视角。

你的任务是审查一个已经完成的代码合并结果，判断合并是否正确且完整。

# 项目背景
{project_context}

# 文件信息
文件路径：{file_path}

# 合并决策记录
- 执行的决策：{decision}
- 决策来源：{decision_source}
- 原始理由：{rationale}

# 原始冲突信息
{original_conflict_summary}

# 合并后的文件内容
```{language}
{merged_content}```

# 审查任务
请从以下维度审查合并结果：

1. **完整性**：下游 fork 的关键私有逻辑是否被保留？
2. **正确性**：上游的重要变更（功能、bugfix、安全修复、新接口）是否被正确引入？
3. **一致性**：合并结果是否内部一致，没有矛盾或遗漏？
4. **安全性**：是否引入了安全风险？
5. **遗留冲突**：文件中是否还存在未解决的冲突标记？

请输出结构化审查结果：
- verdict：PASS / CONDITIONAL / FAIL
- issues：发现的问题列表（每项包含 level、type、description、suggested_fix）
- summary：2-3 句话的总体评价
"""
```

### 4.5 Executor Agent 的 LLM 调用（SEMANTIC_MERGE）

**用途**：将双方修改智能融合为一个版本

**Prompt 框架**：

```python
SEMANTIC_MERGE_PROMPT = """
你是一个精确的代码合并工具。

# 任务
将以下两个版本的代码合并为一个正确的最终版本，要求：
- 保留双方的所有有效修改
- 消除冲突标记
- 保持代码风格一致
- 不添加任何额外的注释或说明文字

# 当前版本（下游 fork）
```{language}
{current_content}```

# 目标版本（上游 upstream）
```{language}
{target_content}```

# 合并分析
{conflict_analysis_rationale}

# 输出要求
直接输出合并后的完整文件内容，不要包含任何解释文字，不要包含 Markdown 代码块标记。
"""
```

---

## 5. 配置文件示例

```yaml
# merge_config.yaml - Multi-agent Code Merge System 配置文件

upstream_ref: "upstream/main"
fork_ref: "feature/private-fork-v2"
working_branch: "merge/auto-{timestamp}"
repo_path: "."
max_files_per_run: 300

project_context: |
  这是一个基于 FastAPI 构建的企业级 REST API 服务。
  下游 fork 在上游基础上添加了私有的多租户认证模块和定制化的数据导出功能。
  上游最近进行了 Python 3.10 → 3.12 升级和 Pydantic v1 → v2 迁移。
  合并目标：将上游的 Pydantic v2 迁移成果引入下游，同时保留所有私有功能。

# 各 Agent 独立 LLM 配置（审查者与执行者使用不同提供商，避免同源偏差）
agents:
  planner:
    provider: "anthropic"
    model: "claude-opus-4-6"
    temperature: 0.2
    max_tokens: 8192
    api_key_env: "ANTHROPIC_API_KEY"

  planner_judge:
    provider: "openai"           # 与 Planner 不同提供商
    model: "gpt-4o"
    temperature: 0.1
    max_tokens: 4096
    api_key_env: "OPENAI_API_KEY"

  conflict_analyst:
    provider: "anthropic"
    model: "claude-sonnet-4-6"
    temperature: 0.3
    max_tokens: 8192
    api_key_env: "ANTHROPIC_API_KEY"

  executor:
    provider: "openai"
    model: "gpt-4o"
    temperature: 0.1
    max_tokens: 16384
    api_key_env: "OPENAI_API_KEY"

  judge:
    provider: "anthropic"        # 与 Executor 不同提供商
    model: "claude-opus-4-6"
    temperature: 0.1
    max_tokens: 8192
    api_key_env: "ANTHROPIC_API_KEY"

  human_interface:
    provider: "anthropic"
    model: "claude-haiku-4-5-20251001"
    temperature: 0.2
    max_tokens: 4096
    api_key_env: "ANTHROPIC_API_KEY"

max_plan_revision_rounds: 2     # PlannerJudge 最多要求 Planner 修订 2 轮

thresholds:
  auto_merge_confidence: 0.85
  human_escalation: 0.60
  risk_score_low: 0.30
  risk_score_high: 0.60

file_classifier:
  excluded_patterns:
    - "**/*.lock"
    - "**/node_modules/**"
    - "**/__pycache__/**"
    - "**/.git/**"
    - "**/dist/**"
    - "**/build/**"
  binary_extensions:
    - ".png"
    - ".jpg"
    - ".gif"
    - ".pdf"
    - ".zip"
    - ".whl"
    - ".egg"
  always_take_target_patterns:
    - "**/requirements*.txt"
    - "**/pyproject.toml"
    - "**/setup.cfg"
  always_take_current_patterns:
    - "**/config/private/**"
    - "**/.env.example"
  security_sensitive:
    patterns:
      - "**/auth/**"
      - "**/security/**"
      - "**/middleware/auth*"
      - "**/*secret*"
      - "**/*credential*"
      - "**/*token*"
      - "**/*.pem"
      - "**/*.key"
    always_require_human: true

# human_decision_timeout_hours 已移除。
# 系统不提供超时默认决策，人工裁决必须显式完成。
# 如需提醒通知，使用：
# notification_interval_hours: 24

output:
  directory: "./outputs"
  formats:
    - "json"
    - "markdown"
  include_raw_diffs: false
  include_llm_traces: false
```

---

## 6. 示例输出文档模板

### 6.1 MergePlan 示例

```json
{
  "plan_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-03-28T10:00:00Z",
  "upstream_ref": "upstream/main",
  "fork_ref": "feature/private-fork-v2",
  "merge_base_commit": "a1b2c3d4e5f6",
  "risk_summary": {
    "total_files": 156,
    "auto_safe_count": 89,
    "auto_risky_count": 34,
    "human_required_count": 18,
    "deleted_only_count": 7,
    "binary_count": 5,
    "excluded_count": 3,
    "estimated_auto_merge_rate": 0.79,
    "top_risk_files": [
      "src/auth/jwt_handler.py",
      "src/core/middleware.py",
      "src/models/user.py"
    ]
  },
  "project_context_summary": "FastAPI 企业服务，需将 Pydantic v2 迁移引入下游，同时保留多租户认证和定制导出功能。主要风险集中在认证模块和核心数据模型。",
  "phases": [
    {
      "batch_id": "phase2-batch-1",
      "phase": "auto_merge",
      "file_paths": ["src/utils/helpers.py", "tests/unit/test_utils.py"],
      "risk_level": "auto_safe",
      "can_parallelize": true
    }
  ],
  "version": "1.0"
}
```

### 6.2 HumanReport 示例（Markdown）

```markdown
# 合并决策请求报告

**运行 ID**: 550e8400-e29b-41d4-a716-446655440000
**生成时间**: 2026-03-28 10:30:00
**待决策项**: 18 个文件，共 42 个冲突点

---

## 总览

| 优先级 | 数量 | 说明 |
|--------|------|------|
| HIGH   | 5    | 涉及认证逻辑或接口变更 |
| MEDIUM | 9    | 业务逻辑冲突 |
| LOW    | 4    | 配置或注释冲突 |

---

## 第 1 项（共 18 项）

**文件**: `src/auth/jwt_handler.py`
**优先级**: HIGH
**冲突类型**: LOGIC_CONTRADICTION

### 问题描述
上游将 JWT 验证库从 `python-jose` 升级到 `authlib`，接口完全不兼容。
下游在 `python-jose` 基础上添加了多租户 token 分发逻辑。

### 上游变更摘要
重构 JWT 验证使用 `authlib.jose`，删除了 `python-jose` 依赖，
新增了 JWKS 自动刷新机制（每 1 小时）。

### 下游变更摘要
在原 `python-jose` 实现基础上，增加了 `tenant_id` claim 的提取和验证，
以及租户级别的 token 黑名单检查。

### AI 分析
**建议**: ESCALATE_HUMAN
**置信度**: 0.42
**分析**: 两个变更在接口层面完全冲突，且涉及安全敏感代码。
下游的多租户逻辑需要移植到 `authlib` 实现上，但这需要理解业务需求。

### 您的选项

**A. TAKE_CURRENT** — 保留下游版本（保留多租户逻辑，不引入 authlib）
> 风险：丢失上游的 JWKS 自动刷新机制

**B. TAKE_TARGET** — 采用上游版本（引入 authlib，但丢失多租户逻辑）
> 风险：多租户功能完全失效，须手动补全

**C. MANUAL_PATCH** — 我来提供手工合并后的代码
> 适用：开发者了解两边逻辑，可自行提供正确版本

---

您的选择（填写 A / B / C）: ____
手工代码（选 C 时必填，粘贴完整文件内容）:
补充说明: ____

---
```

### 6.3 JudgeReport 示例

```json
{
  "verdict_id": "judge-001",
  "verdict": "conditional",
  "reviewed_files_count": 52,
  "passed_files": ["src/utils/helpers.py", "src/models/base.py"],
  "failed_files": [],
  "conditional_files": ["src/core/middleware.py"],
  "issues": [
    {
      "issue_id": "issue-001",
      "file_path": "src/core/middleware.py",
      "issue_level": "medium",
      "issue_type": "missing_logic",
      "description": "下游的请求日志中间件在合并后丢失了 request_id 注入逻辑（第 47-52 行）",
      "affected_lines": [47, 48, 49, 50, 51, 52],
      "suggested_fix": "在 middleware.py 的 dispatch 方法中，于调用 call_next 之前添加 request.state.request_id = uuid4() 赋值",
      "must_fix_before_merge": false
    }
  ],
  "critical_issues_count": 0,
  "high_issues_count": 0,
  "overall_confidence": 0.91,
  "summary": "合并结果总体质量良好，52 个文件中仅发现 1 个 MEDIUM 级别问题。主要风险已通过人工决策妥善处理。建议修复 request_id 注入问题后推进合并。",
  "blocking_issues": [],
  "timestamp": "2026-03-28T14:00:00Z",
  "judge_model": "claude-opus-4-5"
}
```

### 6.4 FinalSummary 示例（Markdown）

```markdown
# 合并最终摘要报告

**项目**: FastAPI 企业服务
**合并来源**: `feature/private-fork-v2` → 基于 `upstream/main`
**执行时间**: 2026-03-28 10:00 ~ 14:30（约 4.5 小时）
**运行 ID**: 550e8400-e29b-41d4-a716-446655440000

---

## 执行结果

| 指标 | 数值 |
|------|------|
| 总处理文件数 | 156 |
| 自动合并成功 | 123 (78.8%) |
| 人工决策处理 | 18 (11.5%) |
| 跳过/排除 | 15 (9.6%) |
| Judge 审查结果 | CONDITIONAL → PASS（修复后） |

---

## 关键决策摘要

### 自动处理亮点
- 成功识别并合并了 34 个 Pydantic v1→v2 的语义等价迁移（API 签名不变）
- 自动保留了 89 个纯依赖更新文件（requirements.txt 采用上游版本）

### 人工决策摘要
| 文件 | 决策 | 说明 |
|------|------|------|
| `src/auth/jwt_handler.py` | MANUAL_PATCH | 开发者手工移植多租户逻辑到 authlib |
| `src/models/user.py` | SEMANTIC_MERGE | AI 融合了 Pydantic v2 迁移和租户字段扩展 |

### 被丢弃的内容
| 文件 | 丢弃原因 |
|------|----------|
| `src/deprecated/old_auth.py` | 上游已彻底删除，下游无私有改动 |

---

## 风险提示

- `src/auth/jwt_handler.py` 涉及安全认证，建议进行独立安全审查
- `src/core/middleware.py` 存在 MEDIUM 级别问题（request_id 注入），已通过 Judge CONDITIONAL 标注

---

## 后续步骤

1. [ ] 修复 `src/core/middleware.py` 中的 request_id 注入问题
2. [ ] 对认证模块进行安全测试
3. [ ] 运行完整测试套件验证合并结果
4. [ ] Code Review 合并后的差异

---

*本报告由 Multi-agent Code Merge System v1.0 自动生成*
*完整决策记录保存在: `./outputs/file_decisions/`*
```

---

## 7. 运行方式说明

### 7.1 安装

```bash
# 克隆仓库
git clone <repo_url>
cd CodeMergeSystem

# 创建虚拟环境并安装依赖
python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

### 7.2 配置

```bash
# 复制示例配置
cp config/merge_config.example.yaml my_merge_config.yaml

# 编辑配置（填写 upstream_ref、fork_ref、project_context 等）
vim my_merge_config.yaml

# 设置 LLM API Key（通过环境变量，不要写入配置文件）
export ANTHROPIC_API_KEY=sk-ant-...
# 或
export OPENAI_API_KEY=sk-...
```

### 7.3 执行完整合并流程

```bash
# 基本用法
merge run --config my_merge_config.yaml

# 指定输出目录
merge run --config my_merge_config.yaml --output ./my_outputs

# 仅运行到 Phase 3（不触发人工决策，用于预览）
merge run --config my_merge_config.yaml --stop-before human_review

# 详细日志模式
merge run --config my_merge_config.yaml --verbose

# 试运行（不实际写入文件）
merge run --config my_merge_config.yaml --dry-run
```

### 7.4 断点续传

```bash
# 列出所有可用检查点
merge checkpoints --run-id 550e8400

# 从最新检查点恢复
merge resume --run-id 550e8400

# 从指定检查点恢复
merge resume --checkpoint ./outputs/checkpoints/run_550e8400_awaiting_human.json

# 在文件批注模式下，填写完决策文件后恢复
merge resume --run-id 550e8400 --decisions ./outputs/human_decisions.yaml
```

### 7.5 仅生成报告

```bash
# 基于已有运行结果重新生成报告（不重新执行合并）
merge report --run-id 550e8400 --format markdown

# 生成特定报告
merge report --run-id 550e8400 --type human_report
merge report --run-id 550e8400 --type judge_report
merge report --run-id 550e8400 --type final_summary
```

### 7.6 验证配置

```bash
# 验证配置文件格式和内容
merge validate --config my_merge_config.yaml

# 检查 Git refs 是否有效
merge validate --config my_merge_config.yaml --check-refs

# 输出预期处理的文件统计（不执行实际合并）
merge validate --config my_merge_config.yaml --preview
```

### 7.7 回滚操作

```bash
# 回滚工作分支上的所有变更
merge rollback --run-id 550e8400

# 仅回滚特定文件
merge rollback --run-id 550e8400 --file src/auth/jwt_handler.py
```

---

## 8. 后续可增强方向

### 8.1 GitHub PR 集成

将 `HumanReport` 直接发布为 GitHub Pull Request 的 Review Comments，开发者可在 PR 界面直接做出 Approve/Request Changes 决策：

```
merge run --config ... --github-pr 123
```

系统自动：
- 将每个待决策项发布为 PR Comment
- 监听 Comment 回复，解析为 `MergeDecision`
- 决策收集完成后自动继续执行

### 8.2 CI/CD 集成

提供 GitHub Actions / GitLab CI 专用模式：

```yaml
# .github/workflows/auto-merge.yml
- name: Run Code Merge System
  run: merge run --config merge_config.yaml --ci-mode
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

CI 模式下：
- 禁用 AWAITING_HUMAN（全部升级为 `ESCALATE_HUMAN` 并记录）
- 输出结构化 JSON 报告供 CI 系统读取
- 退出码：0（PASS）/ 1（CONDITIONAL）/ 2（FAIL）/ 3（需要人工）

### 8.3 Web UI

为 HumanInterface 提供 Web 界面，替代 CLI 交互模式：

```
merge serve --run-id 550e8400 --port 8080
```

功能：
- 富文本 Diff 对比视图（side-by-side）
- 实时预览合并结果
- 批量决策界面
- 团队协作（多人同时审查不同文件）

### 8.4 增量合并模式

支持持续集成场景：不等到分叉积累太多，每周或每次上游 release 时自动处理新增的 diff：

```
merge incremental --since-tag v2.1.0 --config merge_config.yaml
```

### 8.5 合并质量学习

记录每次合并的决策数据，训练本地分类模型，随着使用次数增加，提升风险评分和策略选择的准确度：

- 记录人工决策覆盖 AI 建议的模式
- 定期生成"AI 建议 vs 人工决策"的差异分析报告
- 基于历史数据微调置信度阈值

### 8.6 多仓库合并协调

对于微服务架构，支持跨仓库的合并协调：

- 统一分析多个仓库的 diff
- 识别跨仓库的接口依赖变更
- 生成跨仓库的合并顺序建议
