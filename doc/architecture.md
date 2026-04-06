# 系统架构设计文档

## 目录

1. [问题背景与设计目标](#1-问题背景与设计目标)
2. [核心设计原则](#2-核心设计原则)
3. [项目目录结构](#3-项目目录结构)
4. [技术栈选型](#4-技术栈选型)
5. [模块职责说明](#5-模块职责说明)
6. [系统扩展点设计](#6-系统扩展点设计)

---

## 1. 问题背景与设计目标

### 1.1 问题背景

在长期维护的软件项目中，常见一种高风险场景：**下游团队基于某一上游版本创建了长期分叉分支**（fork branch），在此基础上累积了大量私有改动；与此同时，上游主干持续演进，引入了架构升级、接口变更、依赖更新等大量变更。

当两个分支的历史分叉点已经非常久远时，直接执行 `git merge` 会产生以下问题：

- **冲突数量庞大**：数百乃至数千个文件同时报冲突，人工无法逐一处理。
- **语义信息丢失**：`git` 的行级别 diff 无法理解代码的语义，频繁误判。
- **上下文缺失**：开发者不清楚每个冲突的"修改意图"，无法做出正确选择。
- **不可逆风险**：错误的合并决策可能导致功能缺失或安全漏洞，且难以追溯。
- **人工审查瓶颈**：依赖单一人工审查效率低下，难以在合理时间内完成。

### 1.2 设计目标

本系统（Multi-agent Code Merge System）旨在解决上述问题，具体目标如下：

| 目标 | 描述 |
|------|------|
| **自动化分类** | 将所有变更文件按风险等级分类，优先自动处理低风险文件 |
| **语义级合并** | 对高冲突文件使用 LLM 进行语义理解，生成合并建议 |
| **人工决策支持** | 将无法自动解决的冲突结构化呈现给人工，降低决策成本 |
| **完整审计链** | 每个合并决策均有完整的推理记录，可追溯、可解释 |
| **门禁控制** | Judge Agent 独立审查，确保合并质量满足预设标准才能推进 |
| **安全可回滚** | 全流程支持断点续传，任何阶段均可安全中断和恢复 |

---

## 2. 核心设计原则

### P1：不丢失原则（No-Loss Guarantee）
任何合并决策都不得在无记录的情况下丢弃代码。若某段代码被决定舍弃，必须在 `FileDecisionRecord` 中明确记录"被丢弃的内容"及"丢弃原因"。

### P2：语义优先（Semantic-First）
优先基于代码语义而非文本行差异做决策。对于逻辑功能等价的变更（如变量重命名、函数提取），应识别为"无冲突"或"低风险"。

### P3：可解释性（Explainability）
每一个 `MergeDecision` 必须附带推理说明（`rationale` 字段）。系统输出的所有报告必须对人类可读、逻辑清晰。

### P4：不确定即升级（Uncertainty Escalation）
当 Agent 对某个决策的置信度低于阈值时，必须升级为 `ESCALATE_HUMAN`，绝不允许以"低置信度"决策直接写入代码。

### P5：审查隔离（Review Isolation）
Judge/Reviewer Agent 只读访问合并结果，不直接执行任何写操作。写操作只由 Executor Agent 执行，且必须在 Judge 审查通过后进行。

---

## 3. 项目目录结构

```
CodeMergeSystem/
├── src/
│   ├── agents/                      # 六大核心 Agent 实现
│   │   ├── __init__.py
│   │   ├── base_agent.py            # Agent 抽象基类
│   │   ├── planner_agent.py         # Planner：分析 diff，制定合并计划
│   │   ├── planner_judge_agent.py   # PlannerJudge：独立审查合并计划质量
│   │   ├── executor_agent.py        # Executor：执行自动合并操作（含计划质疑）
│   │   ├── conflict_analyst_agent.py # ConflictAnalyst：深度冲突分析
│   │   ├── judge_agent.py           # Judge/Reviewer：只读审查合并结果
│   │   └── human_interface_agent.py  # HumanInterface：人工决策收集
│   │
│   ├── core/                        # 核心调度与状态管理
│   │   ├── __init__.py
│   │   ├── orchestrator.py          # 主编排器，Phase 顺序调度
│   │   ├── state_machine.py         # 全局状态机
│   │   ├── message_bus.py           # Agent 间消息传递
│   │   ├── checkpoint.py            # 断点保存与恢复
│   │   └── phase_runner.py          # 单 Phase 执行器，支持并发
│   │
│   ├── tools/                       # 工具层（Git 操作、文件 I/O）
│   │   ├── __init__.py
│   │   ├── git_tool.py              # GitPython 封装：diff、checkout、apply
│   │   ├── file_classifier.py       # 文件风险分类器
│   │   ├── diff_parser.py           # Diff 解析与结构化
│   │   ├── patch_applier.py         # Patch 生成与应用
│   │   └── report_writer.py         # 报告序列化输出（JSON/Markdown）
│   │
│   ├── models/                      # 数据模型（Pydantic v2）
│   │   ├── __init__.py
│   │   ├── config.py                # MergeConfig 输入配置模型
│   │   ├── diff.py                  # FileDiff、ConflictPoint 模型
│   │   ├── decision.py              # MergeDecision、FileDecisionRecord
│   │   ├── plan.py                  # MergePlan、Phase 模型
│   │   ├── judge.py                 # JudgeVerdict 模型
│   │   ├── human.py                 # HumanDecisionRequest 模型
│   │   ├── state.py                 # MergeState 全局状态
│   │   ├── plan_review.py           # PlanReviewRound / PlanHumanReview 计划审查记录
│   │   └── message.py               # AgentMessage 消息协议
│   │
│   ├── llm/                         # LLM 调用封装
│   │   ├── __init__.py
│   │   ├── client.py                # LLMClientFactory：按 Agent 配置创建 client
│   │   ├── prompts/                 # Prompt 模板目录
│   │   │   ├── planner_prompts.py
│   │   │   ├── planner_judge_prompts.py  # PlannerJudge 专用 Prompt
│   │   │   ├── analyst_prompts.py
│   │   │   ├── judge_prompts.py
│   │   │   └── executor_prompts.py
│   │   └── response_parser.py       # LLM 响应结构化解析
│   │
│   └── cli/                         # CLI 入口
│       ├── __init__.py
│       ├── main.py                  # Click 主命令组
│       ├── commands/
│       │   ├── run.py               # merge run 命令
│       │   ├── resume.py            # merge resume 命令
│       │   ├── report.py            # merge report 命令
│       │   └── validate.py          # merge validate 命令
│       └── display.py               # Rich 终端输出格式化
│
├── tests/
│   ├── unit/
│   │   ├── test_file_classifier.py
│   │   ├── test_diff_parser.py
│   │   ├── test_state_machine.py
│   │   └── test_models.py
│   ├── integration/
│   │   ├── test_planner_agent.py
│   │   ├── test_executor_agent.py
│   │   └── test_orchestrator.py
│   ├── fixtures/
│   │   ├── sample_diffs/
│   │   └── sample_configs/
│   └── conftest.py
│
├── config/
│   ├── merge_config.example.yaml    # 配置文件示例
│   └── default_thresholds.yaml     # 默认评分阈值配置
│
├── outputs/                         # 运行输出目录（gitignored）
│   ├── merge_plan.json
│   ├── file_decisions/
│   ├── human_report.md
│   ├── judge_report.json
│   └── final_summary.md
│
├── pyproject.toml                   # 项目依赖与构建配置
├── Makefile                         # 常用开发命令
└── README.md
```

---

## 4. 技术栈选型

### 4.1 核心语言与运行时

| 组件 | 选型 | 版本 | 理由 |
|------|------|------|------|
| 主语言 | Python | 3.11+ | asyncio 成熟、LLM SDK 生态最佳 |
| 类型系统 | Pydantic v2 | ≥2.5 | 高性能数据验证，内置 JSON 序列化 |
| 异步运行时 | asyncio + anyio | 内置 | 并发执行多个文件分析任务 |

### 4.2 Git 操作

| 组件 | 选型 | 说明 |
|------|------|------|
| Git 库 | GitPython | 封装 `git diff`、`git show`、`git apply` |
| Diff 解析 | unidiff | 结构化解析 unified diff 格式 |
| Patch 应用 | subprocess + git apply | 原子性应用合并结果 |

### 4.3 LLM 集成

| 组件 | 选型 | 说明 |
|------|------|------|
| Anthropic SDK | anthropic-sdk-python | 调用 Claude 模型进行语义分析 |
| OpenAI SDK | openai | 备用模型支持 |
| 重试机制 | tenacity | 指数退避重试，避免 API 限流 |
| 结构化输出 | Instructor / 原生 tool_use | 确保 LLM 输出符合 Pydantic 模型 |

### 4.4 CLI 与输出

| 组件 | 选型 | 说明 |
|------|------|------|
| CLI 框架 | Click | 子命令、参数解析、帮助文档 |
| 终端 UI | Rich | 进度条、彩色输出、表格展示 |
| 报告格式 | Markdown + JSON | 人类可读 + 机器可处理双格式输出 |

### 4.5 测试与质量

| 组件 | 选型 | 说明 |
|------|------|------|
| 测试框架 | pytest + pytest-asyncio | 支持异步测试用例 |
| Mock | pytest-mock + respx | 隔离 LLM API 调用 |
| 覆盖率 | pytest-cov | 确保 80%+ 测试覆盖率 |
| 类型检查 | mypy | 静态类型验证 |
| 代码格式 | ruff + black | 统一代码风格 |

---

## 5. 模块职责说明

### 5.1 `src/agents/` — Agent 层

本层包含所有 AI Agent 的实现，每个 Agent 继承自 `BaseAgent`，具备以下标准接口：

```python
class BaseAgent(ABC):
    def __init__(self, llm_config: AgentLLMConfig):
        self.llm = LLMClientFactory.create(llm_config)

    async def run(self, state: MergeState) -> AgentMessage:
        """主执行入口，接收全局状态，返回消息"""
        ...

    async def can_handle(self, state: MergeState) -> bool:
        """判断当前状态是否满足该 Agent 的执行前置条件"""
        ...
```

六个 Agent 及职责：

| Agent | 文件 | 核心职责 |
|-------|------|---------|
| Planner | `planner_agent.py` | 分析 diff，生成 MergePlan |
| **PlannerJudge** | `planner_judge_agent.py` | 独立审查 MergePlan 质量，可要求 Planner 修订（最多 2 轮） |
| ConflictAnalyst | `conflict_analyst_agent.py` | 高风险冲突语义分析 |
| Executor | `executor_agent.py` | 唯一写权限 Agent，执行合并；可发起 PlanDisputeRequest |
| Judge | `judge_agent.py` | 只读审查合并结果，输出 JudgeVerdict |
| HumanInterface | `human_interface_agent.py` | 人工决策收集与呈现 |

各 Agent 详细职责见 `agents-design.md`。

### 5.2 `src/core/` — 编排层

- **`orchestrator.py`**：系统主入口，按 Phase 顺序调度 Agent，管理整体执行流程。
- **`state_machine.py`**：维护 `MergeState`，处理状态转换，记录每次状态变更的时间戳和触发原因。
- **`message_bus.py`**：基于内存的简单消息队列，Agent 通过此总线发布和订阅消息。
- **`checkpoint.py`**：将 `MergeState` 序列化至磁盘（JSON），支持从任意检查点恢复。
- **`phase_runner.py`**：单 Phase 内的任务执行器，使用 `asyncio.gather` 支持并发文件处理。

### 5.3 `src/tools/` — 工具层

工具层不包含业务逻辑，只提供纯函数式的工具调用接口：

- **`git_tool.py`**：封装所有 `git` 命令，对外暴露高级 API（如 `get_file_diff(file_path)`）。
- **`file_classifier.py`**：基于文件路径、扩展名、diff 大小、冲突密度计算风险分数。
- **`diff_parser.py`**：将 unified diff 文本解析为结构化的 `FileDiff` 和 `ConflictPoint` 列表。
- **`patch_applier.py`**：将 LLM 生成的合并结果转换为 git patch 并原子性应用。
- **`report_writer.py`**：将各类数据模型序列化为 Markdown 报告或 JSON 文件。包括 `write_plan_review_report()` 用于输出 Planner↔Judge 全部交互记录和人类审查记录（`plan_review_<run_id>.md`）。

### 5.4 `src/models/` — 数据层

所有数据模型使用 Pydantic v2 定义，具备完整类型注解和验证规则。模型详细定义见 `data-models.md`。

### 5.5 `src/llm/` — LLM 层

- **`client.py`**：`LLMClientFactory` 工厂类，按每个 Agent 的 `AgentLLMConfig` 创建独立客户端，支持 Anthropic / OpenAI，各 Agent 可使用不同提供商与模型。
- **`prompts/`**：每个 Agent 对应独立的 Prompt 模板文件，模板使用 Jinja2 渲染。
- **`response_parser.py`**：解析 LLM 响应，使用 Instructor 库将非结构化文本转换为 Pydantic 模型。

### 5.6 `src/cli/` — CLI 层

基于 Click 构建，提供以下子命令：

```
merge run      --config <yaml>      执行完整合并流程
merge resume   --checkpoint <path>  从检查点恢复执行
merge report   --output <dir>       仅生成报告（不执行合并）
merge validate --config <yaml>      验证配置文件合法性
```

---

## 6. 系统扩展点设计

### 6.1 新增 Agent

继承 `BaseAgent`，实现 `run()` 和 `can_handle()` 方法，在 `orchestrator.py` 的 Phase 配置中注册即可。不需要修改任何现有 Agent 代码。

### 6.2 新增合并策略

在 `src/tools/patch_applier.py` 中扩展 `MergeStrategy` 枚举，并在 `executor_agent.py` 的策略分发函数中添加对应处理分支。

### 6.3 更换 LLM 提供商

修改 `src/llm/client.py` 中的 `LLMProvider` 枚举及对应的客户端初始化逻辑，或通过 `merge_config.yaml` 中的 `llm.provider` 字段动态切换。

### 6.4 接入外部系统

- **GitHub PR**：在 `report_writer.py` 中添加 GitHub API 客户端，将 `HumanReport` 转换为 PR Review Comment。
- **CI/CD**：提供 `merge validate` 命令的退出码标准，CI 可通过退出码判断是否允许合并。
- **Web UI**：`HumanInterface` Agent 支持切换至 HTTP 模式，通过 REST API 接收人工决策（替换当前的 CLI stdin 模式）。

### 6.5 自定义文件分类规则

在 `config/merge_config.yaml` 中配置 `file_classifier.rules` 字段，支持基于 glob 模式、文件大小、历史修改频率等维度自定义风险评分规则，无需修改代码。
