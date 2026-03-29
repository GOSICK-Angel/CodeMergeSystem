# Phase 1.2 增强功能实施计划

> **前置条件**：P0 MVP 已全部完成并通过测试（90% 覆盖率）。
> **本文档用途**：供新会话直接执行的完整实施指南。
> **权威设计文档**：`doc/implementation-plan.md` §1.2、`doc/agents-design.md`、`doc/data-models.md`、`doc/flow.md`

---

## 目录

1. [功能清单与优先级排序](#1-功能清单与优先级排序)
2. [实施顺序与依赖关系](#2-实施顺序与依赖关系)
3. [Feature A：文件批注模式](#3-feature-a文件批注模式)
4. [Feature B：LLM 辅助风险评分](#4-feature-b-llm-辅助风险评分)
5. [Feature C：相似冲突批量决策](#5-feature-c相似冲突批量决策)
6. [Feature D：静态语法检查集成](#6-feature-d静态语法检查集成)
7. [Feature E：CI/CD 集成支持](#7-feature-e-cicd-集成支持)
8. [Feature F：GitHub PR 集成](#8-feature-f-github-pr-集成)
9. [Feature G：Web UI](#9-feature-g-web-ui)
10. [集成验证检查点](#10-集成验证检查点)

---

## 1. 功能清单与优先级排序

| 优先级 | Feature | 说明 | 预估复杂度 | 外部依赖 |
|--------|---------|------|-----------|----------|
| P1-A | 文件批注模式 | 生成可批注 YAML + `resume` 读取 | 低 | 无 |
| P1-B | LLM 辅助风险评分 | 结合代码语义提升评分准确度 | 中 | LLM API |
| P1-C | 相似冲突批量决策 | 识别同类冲突，一键批量处理 | 中 | 无 |
| P1-D | 静态语法检查集成 | Phase 5 对 Python/JS/TS 做语法验证 | 低 | `ast`/`esprima` |
| P1-E | CI/CD 集成支持 | 标准退出码 + JSON 报告供 CI 读取 | 低 | 无 |
| P1-F | GitHub PR 集成 | HumanReport 发布为 PR Review Comments | 中 | GitHub API |
| P1-G | Web UI | 替换 CLI 交互为 Web 表单 | 高 | FastAPI + 前端 |

---

## 2. 实施顺序与依赖关系

```
Round 1（无外部依赖，可并行）:
  ├── Feature A: 文件批注模式
  ├── Feature D: 静态语法检查集成
  └── Feature E: CI/CD 集成支持

Round 2（依赖 Round 1 稳定）:
  ├── Feature B: LLM 辅助风险评分
  └── Feature C: 相似冲突批量决策

Round 3（需外部 API / 额外框架）:
  ├── Feature F: GitHub PR 集成
  └── Feature G: Web UI（独立子项目）
```

---

## 3. Feature A：文件批注模式

### 3.1 目标

让用户以离线方式审查冲突：`merge run` 生成一个可编辑的 YAML 文件，用户编辑后通过 `merge resume --decisions <path>` 读取决策继续执行。

### 3.2 现状分析

- `HumanInterfaceAgent.collect_decisions_file()` 已存在基础实现（`src/agents/human_interface_agent.py:169`），可读取 YAML 决策文件
- `HumanInterfaceAgent.generate_report()` 已有报告生成能力
- 缺少：**批注模板生成** 和 **CLI `--export-decisions` 选项**

### 3.3 实施步骤

#### Step 1: 新增批注 YAML 模板生成器

**文件**: `src/tools/decision_template.py`（新建）

```
功能：
- generate_decision_template(requests: list[HumanDecisionRequest], state: MergeState) -> str
- 为每个待决策文件生成结构化 YAML 块，包含：
  - file_path, risk_level, conflict_summary
  - options（可选决策枚举）
  - decision: ""（待用户填写）
  - reviewer_name: ""
  - reviewer_notes: ""
  - custom_content: ""（仅 MANUAL_PATCH 时需要）
- 文件头包含使用说明注释
```

#### Step 2: CLI 新增 `--export-decisions` 选项

**文件**: `src/cli/main.py` — 修改 `run_command`

```
变更：
- run_command 新增 --export-decisions <path> 选项
- 当流程进入 AWAITING_HUMAN 阶段时，自动导出决策模板到指定路径
- 打印提示信息：编辑文件后用 merge resume --decisions <path> 继续
```

#### Step 3: CLI `resume` 支持 `--decisions` 参数

**文件**: `src/cli/commands/resume.py` — 修改

```
变更：
- 新增 --decisions <path> 参数
- 恢复 checkpoint 后，调用 collect_decisions_file() 读取用户决策
- 将决策注入 state，继续后续 Phase
```

#### Step 4: 单元测试

**文件**: `tests/unit/test_decision_template.py`（新建）

```
测试项：
- 模板生成格式正确性
- 包含所有待决策文件
- 生成 → 填写 → 读取的完整 round-trip
- 空决策文件的容错处理
```

---

## 4. Feature B: LLM 辅助风险评分

### 4.1 目标

在规则评分基础上，调用 LLM 分析代码语义，得到更准确的风险评分。

### 4.2 现状分析

- `file_classifier.py` 已有 `compute_risk_score()`，纯规则算法
- `planner_agent.py` 的 `classify_all_files()` 调用规则评分后生成计划
- 需要：在规则评分后增加一个可选的 LLM 辅助评分步骤

### 4.3 实施步骤

#### Step 1: 新增 LLM 风险评分 Prompt

**文件**: `src/llm/prompts/risk_scoring_prompts.py`（新建）

```
功能：
- build_risk_scoring_prompt(file_diff: FileDiff, rule_score: float) -> str
- 输入：文件 diff 摘要、规则评分、文件类型
- 输出要求：JSON { "llm_risk_score": float, "reasoning": str, "risk_factors": list[str] }
- 约束：LLM 评分仅作为调整因子，不完全替代规则评分
```

#### Step 2: 扩展 file_classifier

**文件**: `src/tools/file_classifier.py` — 修改

```
变更：
- 新增 async compute_llm_risk_score(file_diff, llm_client, rule_score) -> float
- 混合评分公式：final = 0.6 * rule_score + 0.4 * llm_score
- 当 LLM 不可用时 graceful fallback 到纯规则评分
```

#### Step 3: Planner Agent 集成

**文件**: `src/agents/planner_agent.py` — 修改

```
变更：
- classify_all_files() 检查 config 中是否启用 LLM 风险评分
- 启用时，对规则评分处于 [0.25, 0.65] 的"灰区"文件调用 LLM 评分
- 不在明确高/低风险文件上浪费 LLM 调用
```

#### Step 4: 配置扩展

**文件**: `src/models/config.py` — 修改

```
变更：
- MergeConfig 新增可选字段：
  llm_risk_scoring:
    enabled: bool = False
    gray_zone_low: float = 0.25
    gray_zone_high: float = 0.65
    rule_weight: float = 0.6
```

#### Step 5: 单元测试

**文件**: `tests/unit/test_llm_risk_scoring.py`（新建）

```
测试项：
- 混合评分公式正确性
- 灰区过滤逻辑
- LLM 不可用时 fallback
- 配置开关生效
```

---

## 5. Feature C：相似冲突批量决策

### 5.1 目标

识别语义相似的冲突（如多个文件中的相同依赖升级），允许用户一次性做出批量决策。

### 5.2 现状分析

- `ConflictAnalysis` 已有 `similar_conflicts: list[str]` 字段（`src/models/conflict.py:37`）
- `HumanDecisionRequest` 已有 `is_batch_decision: bool` 字段（`src/models/human.py:36`）
- `DecisionSource` 已有 `BATCH_HUMAN` 值（`src/models/decision.py:21`）
- 数据模型已就绪，缺少：**相似性检测算法** 和 **批量决策 UI 逻辑**

### 5.3 实施步骤

#### Step 1: 冲突相似性检测器

**文件**: `src/tools/conflict_grouper.py`（新建）

```
功能：
- group_similar_conflicts(analyses: list[ConflictAnalysis]) -> list[ConflictGroup]
- ConflictGroup: { group_id, conflict_type, pattern_description, file_paths, representative_file }
- 分组规则：
  1. 相同 conflict_type
  2. 相同变更模式（如 "版本号从 X 升级到 Y"）
  3. 相同目录下的同类变更
- 最小分组大小：2 个文件
```

#### Step 2: HumanInterface 批量决策支持

**文件**: `src/agents/human_interface_agent.py` — 修改

```
变更：
- generate_report() 在报告中按分组展示冲突
- collect_decisions_cli() 新增批量决策模式：
  - 识别到分组后提示 "以下 N 个文件有相似冲突，是否统一处理？[Y/n]"
  - 用户选择 Y 后对整组应用同一决策
  - DecisionSource 标记为 BATCH_HUMAN
- collect_decisions_file() 支持 YAML 中的 group_decision 语法
```

#### Step 3: Orchestrator 集成

**文件**: `src/core/orchestrator.py` — 修改

```
变更：
- Phase 4 (AWAITING_HUMAN) 前调用 conflict_grouper
- 将分组信息附加到 HumanDecisionRequest
- 批量决策结果展开为逐文件的 FileDecisionRecord
```

#### Step 4: 单元测试

**文件**: `tests/unit/test_conflict_grouper.py`（新建）

```
测试项：
- 相同 conflict_type 正确分组
- 单文件不成组
- 批量决策正确展开到所有文件
- YAML 批量决策语法解析
```

---

## 6. Feature D：静态语法检查集成

### 6.1 目标

在 Phase 5（Judge 审查）中，对合并后的 Python/JS/TS 文件做语法验证，确保合并结果至少语法正确。

### 6.2 实施步骤

#### Step 1: 语法检查工具

**文件**: `src/tools/syntax_checker.py`（新建）

```
功能：
- check_syntax(file_path: str, content: str) -> SyntaxCheckResult
- SyntaxCheckResult: { valid: bool, errors: list[SyntaxError], language: str }
- 支持的语言和工具：
  - Python: ast.parse()（标准库，无额外依赖）
  - JavaScript/TypeScript: 尝试调用 node --check（可选依赖）
  - JSON/YAML: 标准库解析
- 不可用的语言返回 SyntaxCheckResult(valid=True, errors=[], language="unknown")
```

#### Step 2: Judge Agent 集成

**文件**: `src/agents/judge_agent.py` — 修改

```
变更：
- review_file() 在 LLM 审查前先做语法检查
- 语法错误自动标记为 JudgeIssue(severity="CRITICAL")
- 语法检查失败的文件，verdict 强制为 NEEDS_REVISION
```

#### Step 3: 配置扩展

**文件**: `src/models/config.py` — 修改

```
变更：
- MergeConfig 新增可选字段：
  syntax_check:
    enabled: bool = True
    languages: list[str] = ["python", "javascript", "typescript", "json", "yaml"]
```

#### Step 4: 单元测试

**文件**: `tests/unit/test_syntax_checker.py`（新建）

```
测试项：
- Python 有效/无效代码检测
- JSON/YAML 格式验证
- 未知语言 graceful 跳过
- Judge 集成后语法错误标记为 CRITICAL
```

---

## 7. Feature E: CI/CD 集成支持

### 7.1 目标

让 `merge run` 可以在 CI/CD 管道中无人值守运行，通过退出码和机器可读报告与外部系统集成。

### 7.2 现状分析

- 当前 CLI 使用 `sys.exit(1)` 表示错误，但没有区分错误类型
- JSON 报告已存在（`report_writer.py`），但缺少 CI 专用的摘要格式

### 7.3 实施步骤

#### Step 1: 定义标准退出码

**文件**: `src/cli/exit_codes.py`（新建）

```
EXIT_SUCCESS = 0           # 合并完成，全部通过
EXIT_NEEDS_HUMAN = 10      # 合并暂停，等待人工决策
EXIT_JUDGE_REJECTED = 20   # Judge 审查不通过
EXIT_PARTIAL_FAILURE = 30  # 部分文件处理失败
EXIT_CONFIG_ERROR = 40     # 配置错误
EXIT_GIT_ERROR = 50        # Git 操作失败
EXIT_LLM_ERROR = 60        # LLM API 调用失败
EXIT_UNKNOWN_ERROR = 1     # 未知错误
```

#### Step 2: CLI 新增 `--ci` 模式

**文件**: `src/cli/main.py` — 修改

```
变更：
- run_command 新增 --ci flag
- CI 模式下：
  - 禁用所有交互式 prompt（AWAITING_HUMAN 时自动导出决策文件并退出 code 10）
  - 禁用 Rich 终端样式，输出纯文本日志
  - 运行结束后自动输出 JSON 摘要到 stdout
  - 使用标准退出码
```

#### Step 3: CI 摘要报告

**文件**: `src/tools/report_writer.py` — 修改

```
变更：
- 新增 write_ci_summary(state) -> dict 函数
- 输出结构：
  {
    "status": "success|needs_human|rejected|partial_failure",
    "total_files": int,
    "auto_merged": int,
    "human_required": int,
    "failed": int,
    "judge_verdict": "approved|rejected|mixed",
    "report_path": str,
    "decisions_file": str | null
  }
```

#### Step 4: 单元测试

**文件**: `tests/unit/test_ci_integration.py`（新建）

```
测试项：
- 各退出码映射正确
- CI 模式无交互
- CI 摘要 JSON 格式正确
- AWAITING_HUMAN 时退出码为 10 且决策文件已导出
```

---

## 8. Feature F: GitHub PR 集成

### 8.1 目标

将 HumanReport 自动发布为 GitHub PR Review Comments，让审查者可以在 PR 页面直接批注决策。

### 8.2 实施步骤

#### Step 1: GitHub API 客户端

**文件**: `src/integrations/github_client.py`（新建）

```
功能：
- GitHubClient(token: str, repo: str)
- create_review(pr_number, comments: list[ReviewComment]) -> Review
- update_review_comment(comment_id, body) -> None
- get_review_comments(pr_number) -> list[ReviewComment]
- ReviewComment: { path, line, body, side }
- 使用 httpx async client
- Token 从环境变量 GITHUB_TOKEN 读取
```

#### Step 2: PR Comment 格式化器

**文件**: `src/integrations/github_formatter.py`（新建）

```
功能：
- format_decision_request_as_comment(req: HumanDecisionRequest) -> ReviewComment
- 每个待决策文件生成一条 PR comment，包含：
  - 风险等级标签
  - 冲突摘要
  - 可选决策（以 checkbox 或 /command 方式）
  - 分析师建议
- parse_decision_from_comment(comment_body: str) -> MergeDecision | None
  - 解析用户在 comment 中的决策回复
```

#### Step 3: CLI 集成

**文件**: `src/cli/main.py` — 修改

```
变更：
- run_command 新增 --github-pr <number> 选项
- 进入 AWAITING_HUMAN 时，发布 PR Review
- resume 时，读取 PR comments 中的决策
```

#### Step 4: 配置扩展

**文件**: `src/models/config.py` — 修改

```
变更：
- MergeConfig 新增可选字段：
  github:
    enabled: bool = False
    token_env: str = "GITHUB_TOKEN"
    repo: str = ""  # owner/repo
    pr_number: int | None = None
```

#### Step 5: 单元测试

**文件**: `tests/unit/test_github_integration.py`（新建）

```
测试项：
- Comment 格式化正确性
- Decision 解析覆盖所有 MergeDecision 值
- Token 缺失时 graceful 错误提示
- Mock GitHub API 的 round-trip 测试
```

---

## 9. Feature G: Web UI

### 9.1 目标

提供 Web 界面替代 CLI 交互，支持文件 diff 可视化、决策按钮、批量操作。

### 9.2 技术选型

- **后端**: FastAPI（与现有 async 架构一致）
- **前端**: 轻量 HTML + HTMX（避免引入完整前端构建链）
- **部署**: 本地启动，`merge ui --port 8080`

### 9.3 实施步骤

#### Step 1: Web Server 骨架

**文件**: `src/web/app.py`（新建）

```
功能：
- FastAPI app with CORS
- 路由：
  - GET  /api/status         — 当前合并状态
  - GET  /api/files           — 待决策文件列表
  - GET  /api/files/{path}    — 单文件 diff + 冲突分析
  - POST /api/decisions       — 提交决策
  - POST /api/decisions/batch — 批量决策
  - GET  /api/report          — 最终报告
  - WS   /ws/progress         — 实时进度推送
```

#### Step 2: 前端页面

**文件**: `src/web/templates/`（新建目录）

```
页面：
- index.html     — Dashboard：总览统计 + 文件列表
- file.html      — 单文件详情：diff 视图 + 决策表单
- report.html    — 最终报告展示
- 使用 HTMX 做无刷新交互，Pico CSS 做样式
```

#### Step 3: Orchestrator 集成

**文件**: `src/core/orchestrator.py` — 修改

```
变更：
- AWAITING_HUMAN 阶段支持通过 Web API 收集决策
- 新增 WebDecisionCollector 实现 DecisionCollector 接口
- 通过 WebSocket 推送 Phase 执行进度
```

#### Step 4: CLI 入口

**文件**: `src/cli/main.py` — 修改

```
变更：
- 新增 merge ui 子命令
- 启动 Web Server + 打开浏览器
- 支持 --port, --host 参数
```

#### Step 5: 测试

```
测试项：
- API endpoint 响应格式
- 决策提交 → state 更新 round-trip
- WebSocket 连接与消息格式
- 前端渲染（可选 Playwright E2E）
```

---

## 10. 集成验证检查点

### Round 1 完成后验证

```bash
# Feature A: 文件批注模式
merge run --config test.yaml --export-decisions /tmp/decisions.yaml
# 验证：/tmp/decisions.yaml 包含所有待决策文件
# 编辑决策文件后
merge resume --decisions /tmp/decisions.yaml
# 验证：决策被正确读取，流程继续

# Feature D: 语法检查
pytest tests/unit/test_syntax_checker.py -v
# 验证：Python 语法错误被检出

# Feature E: CI/CD
merge run --config test.yaml --ci
echo $?
# 验证：退出码符合预期（0/10/20/30/40/50/60）
```

### Round 2 完成后验证

```bash
# Feature B: LLM 风险评分
# 在 config.yaml 中设置 llm_risk_scoring.enabled: true
merge run --config test.yaml --dry-run
# 验证：灰区文件有 LLM 辅助评分日志

# Feature C: 批量决策
# 验证：相似冲突分组显示在报告中
# 验证：批量决策正确展开到所有文件
```

### Round 3 完成后验证

```bash
# Feature F: GitHub PR
merge run --config test.yaml --github-pr 42
# 验证：PR 上出现 Review Comments

# Feature G: Web UI
merge ui --port 8080
# 验证：浏览器可访问 Dashboard
# 验证：提交决策后流程继续
```

### 全量回归

```bash
pytest                           # 全部测试通过
mypy src                         # 类型检查通过
ruff check src/                  # Lint 通过
pytest --cov=src --cov-report=term-missing  # 覆盖率 >= 80%
```

---

## 附录：文件变更清单

### 新建文件

| 文件 | Feature | 说明 |
|------|---------|------|
| `src/tools/decision_template.py` | A | YAML 决策模板生成器 |
| `src/llm/prompts/risk_scoring_prompts.py` | B | LLM 风险评分 Prompt |
| `src/tools/conflict_grouper.py` | C | 冲突相似性分组 |
| `src/tools/syntax_checker.py` | D | 静态语法检查 |
| `src/cli/exit_codes.py` | E | 标准退出码定义 |
| `src/integrations/github_client.py` | F | GitHub API 客户端 |
| `src/integrations/github_formatter.py` | F | PR Comment 格式化 |
| `src/web/app.py` | G | FastAPI Web Server |
| `src/web/templates/*.html` | G | 前端模板 |
| `tests/unit/test_decision_template.py` | A | 测试 |
| `tests/unit/test_llm_risk_scoring.py` | B | 测试 |
| `tests/unit/test_conflict_grouper.py` | C | 测试 |
| `tests/unit/test_syntax_checker.py` | D | 测试 |
| `tests/unit/test_ci_integration.py` | E | 测试 |
| `tests/unit/test_github_integration.py` | F | 测试 |

### 修改文件

| 文件 | Feature | 变更点 |
|------|---------|--------|
| `src/agents/human_interface_agent.py` | A, C | 批注模板导出 + 批量决策 |
| `src/tools/file_classifier.py` | B | LLM 辅助评分 |
| `src/agents/planner_agent.py` | B | 灰区文件 LLM 评分集成 |
| `src/agents/judge_agent.py` | D | 语法检查集成 |
| `src/core/orchestrator.py` | C, G | 批量决策 + Web 决策收集 |
| `src/tools/report_writer.py` | E | CI 摘要报告 |
| `src/cli/main.py` | A, E, F, G | CLI 新选项 |
| `src/cli/commands/resume.py` | A | --decisions 参数 |
| `src/models/config.py` | B, D, F | 配置字段扩展 |
