# Claude-Code-Game-Studios 多 Agent 协作模式分析与 CodeMergeSystem 优化方案

> **参考仓库**：[Donchitos/Claude-Code-Game-Studios](https://github.com/Donchitos/Claude-Code-Game-Studios)
> **分析日期**：2026-04-20
> **本文定位**：提炼该项目在「任务分解 + 角色设计」上的可复用模式，并给出对 CodeMergeSystem 的具体改造建议。
> **读者假设**：已熟悉 `doc/architecture.md` 与 `doc/modules/agents.md`。

---

## 1. 参考仓库概览

Claude-Code-Game-Studios（以下简称 **CCGS**）把一次 Claude Code 会话拆成「虚拟游戏工作室」：49 个子 Agent、72 个 Skill（slash command）、12 个 Hook、11 套路径域规则、39 份文档模板。其核心贡献不在于 Agent 数量，而在于**用真实组织学原理约束 LLM 协作的边界**。

与当前 CodeMergeSystem 的差异一句话总结：

> CMS 把 Agent 组织在 **Phase 时间轴**（状态机）上，CCGS 把 Agent 组织在 **职责空间**（组织架构）上。两者正交，可以叠加。

---

## 2. 核心模式提炼

以下 10 项来自 CCGS 的 `.claude/docs/agent-coordination-map.md`、`coordination-rules.md`、`director-gates.md`、`review-workflow.md`，以及各 Agent markdown 的 frontmatter + "Collaboration Protocol" 段落。

### 2.1 三层角色金字塔（Directors / Leads / Specialists）

```
Tier 1 Directors (Opus) —— 守护愿景、跨域仲裁
  creative-director | technical-director | producer

Tier 2 Leads (Sonnet) —— 领域负责人、任务分派
  game-designer | lead-programmer | qa-lead | ...

Tier 3 Specialists (Sonnet/Haiku) —— 动手执行
  gameplay-programmer | level-designer | ui-programmer | ...
```

**关键点**：模型等级与层级绑定——越高层越要"综合多份文档给结论"，越需要 Opus；越底层越"单一文件做修改"，Sonnet / Haiku 足够。这是成本与推理深度的显式权衡。

### 2.2 纵向委派 + 横向磋商的硬边界

| 动作 | 允许 | 禁止 |
|---|---|---|
| Director → Lead | ✅ | Director 直接改 Specialist 领域文件 |
| Lead → Specialist | ✅ | Specialist 越权做跨域决策 |
| 同层 Lead A ↔ Lead B | **可磋商**，不可做绑定决定 | A 直接改 B 的目录 |
| 冲突 | 升级到**共同父级** | 同级私下达成"共识" |

编码体现：每个 Agent 的 markdown 中明示"Domain boundaries"+"Escalation"段落，并与 `.claude/rules/` 路径域规则双重约束（specialist 修改非自己目录的文件会被 hook 拦截）。

### 2.3 Producer：跨域变更的专职协调者

`producer` 不拥有任何领域文件，唯一职责是**当一条需求横跨多个部门时做编排**——登记任务、排期、触发相关 Lead、收集结果、生成 retrospective。在 LLM 体系里这相当于 "router agent"，避免任何一个 Lead 越权"代表全工作室"发言。

### 2.4 Review Modes（审查强度三档用户可调）

`production/review-mode.txt` 里写 `full | lean | solo`，所有 gate-using skill 支持 `--review <mode>` 临时覆盖：

| 模式 | 行为 | 场景 |
|---|---|---|
| full | 每个 workflow step 都跑 Director gate | 团队 / 学习期 |
| lean | 仅 PHASE_GATE（里程碑级） | 默认，solo dev |
| solo | 所有 gate 跳过 | 原型 / 游戏 jam |

**启示**：把「审查强度」从代码里抽出来，作为一级用户配置。

### 2.5 Director Gates 作为可复用 Prompt 清单

`.claude/docs/director-gates.md` 给每个 Director 审查场景分配一个 **gate ID**（如 `CD-PILLARS`、`TD-ARCH-REVIEW`），其他 skill 需要该审查时只引用 ID，不再内联 prompt。集中一处修改、全局生效，避免 prompt 漂移。

### 2.6 Agent 内置的 Collaboration Protocol

每个 Agent 定义里固定一段 5 步协议（样本见 `game-designer.md`）：

```
1. Ask      —— 先问清目标 / 约束 / 参考
2. Options  —— 给 2-4 个选项 + 优缺点（引用设计理论）
3. Decide   —— 用户拍板（强制 AskUserQuestion UI）
4. Draft    —— 渐进写入，写一段、存一段、更新 session-state
5. Approve  —— 每次 Write 前显式确认
```

这把「人机协作节奏」硬编码到 prompt 里，而不是靠上层 Orchestrator 控制。

### 2.7 并行 Task 协议

`Coordination Rules` 明确两类并行：

- **Subagents 并行**：独立输入立即一起发 Task，不等彼此结果。`/review-all-gdds` 的 Phase 1 (consistency) + Phase 2 (design theory) 示范同时发车。
- **Agent Teams 并行**（实验）：跨 session，仅在"工作量 >30min + 文件不重叠 + senior 协调 3+ 子会话"才启用。

### 2.8 Skills 与 Agents 解耦

Skill（slash command）是**工作流单元**，Agent 是**角色**。一个 skill 可以顺序 / 并行调用多个 Agent；一个 Agent 被多个 skill 复用。例子：`/team-release` 是编排器，它按顺序调 `release-manager → qa-lead → localization-lead → performance-analyst → devops-engineer → technical-director`。

### 2.9 9 个标准化工作流模式

`agent-coordination-map.md` 固化了 9 条端到端流水线（Feature / Bug / Balance / Level / Sprint / Milestone / Release / Prototype / Live-Event），每条都是一串确定顺序的 Agent 调用。这使得大部分需求可以 **"选模式→填参数"**，无需临场设计编排。

### 2.10 显式反模式清单

coordination-rules 末尾列出 5 条红线（越级决策 / 跨域实现 / 口头共识 / 单体任务 / 基于假设实现）。反模式写入文档比写"最佳实践"更有约束力——触发时容易立即识别。

---

## 3. 当前项目对照

### 3.1 已具备的同类机制（✅ 保留）

| CCGS 模式 | CMS 对应实现 | 位置 |
|---|---|---|
| Reviewer 与 Executor 模型隔离 | `judge` / `planner_judge` 强制异 provider | `doc/modules/agents.md` §1 |
| 确定性工具 + LLM 双轨验证 | Judge 两段式（确定性流水线 + LLM）、六大丢失扫描器 | `judge_agent.py`, `src/tools/` |
| 置信度阈值决定升级 | `auto_merge_confidence` / `human_escalation` | `MergeConfig.thresholds` |
| Gate 可复用命令清单 | `GateCommandConfig` + `baseline_parsers/` | `src/tools/gate_runner.py` |
| 单一写通道 | Executor + `apply_with_snapshot()` (P7) | `src/tools/patch_applier.py` |
| 模型按复杂度分档 | 每个 Agent 独立 `AgentLLMConfig` | `src/models/config.py` |

### 3.2 尚缺失或可强化的点（✳️ 本方案目标）

| # | 缺口 | 影响 |
|---|---|---|
| **G1** | **Agent 扁平**：7 个 Agent 同级并排，没有 Director/Lead 分层 | Planner 同时负责"策略+分层+安全敏感判定+修订响应"；单 Agent prompt 膨胀到 1003 LOC |
| **G2** | **无 Producer 角色**：跨 Phase 变更（如 plan dispute → 再规划 → 再执行 → 再审）的"编排逻辑"分散在 Orchestrator 里 | Orchestrator 沦为业务判断的容器，未来增加新回环时耦合高 |
| **G3** | **Gate Prompt 内联**：Judge / PlannerJudge 的审查指令写死在各自 agent 里 | 修订审查标准需要动多个文件，容易漂移 |
| **G4** | **Review Mode 不可调**：不存在"full / lean / solo"全局开关 | 小项目想跳过 PlannerJudge / 加速的用户只能手工改 YAML |
| **G5** | **协作协议不显式**：Agent 和人之间的交互协议（何时问、问什么）缺乏统一模板 | HumanInterface 的行为依赖个别 phase 的硬编码字段 |
| **G6** | **无标准 workflow catalog**：跨 Phase 的典型场景（普通合并 / 迁移感知 / 纯 cherry-pick / 仅 dry-run）没有命名 | 用户需要记 `--dry-run` `--ci` 等标志组合，而不是语义名字 |
| **G7** | **反模式未落档**：`CLAUDE.md` 只列正向原则，缺"禁止做什么"清单 | 新贡献者容易在 PR 里引入违反 P5/P7 的代码 |
| **G8** | **并行机会未挖掘**：ConflictAnalyst 对高风险文件目前串行处理 | N 个独立文件诊断延迟线性叠加 |
| **G9** | **任务粒度未硬限制**：Planner 可能生成一个 PhaseFileBatch 含 50+ 文件 | 单批次失败回滚代价大，且超出 LLM 注意力半径 |

---

## 4. 优化方案

> **一句话概括**：给每个 Agent 发一张"岗位说明书"，给用户一张"菜单"，给并行任务一套"流水线"，给异常情况一个"值班长"。四件事互不重叠，合起来覆盖第 3 节列出的全部缺口。

### 缺口与方案的对应

| 缺口（§3.2） | 由哪件事解决 |
|---|---|
| G3 / G5 / G7（prompt 散落、协作协议缺失、反模式未落档） | **O-A 岗位说明书** |
| G4 / G6（审查强度不可调、工作流无命名） | **O-B 菜单** |
| G8（并行机会未用上） | **O-C 流水线** |
| G1 / G2 / G9（Agent 扁平、无协调者、任务粒度失控） | **O-D 值班长** |

---

### O-A. 给每个 Agent 发"岗位说明书"（Agent Contract）

**问题**：现在 Planner 的行为规则（该读哪些字段、该调哪些 prompt、不能做什么）分散在 1000 行代码和几份 CLAUDE.md 文档里。改一次要翻好几个地方，新人也搞不清楚边界。

**做法**：每个 Agent 配一份 yaml 文件作为"岗位说明书"，集中写清四件事：

1. **能读什么**（输入字段白名单）
2. **要输出什么**（Pydantic 类名）
3. **能调哪些 prompt 模板**（从统一的 prompt 库里选，不再内联写死）
4. **绝对不能做什么**（比如 Judge 不能写 state、Planner 不能给缺失字段填默认值）

举例：

```yaml
# contracts/planner.yaml
能读:    [file_diffs, file_classifications, migration_info]
输出:    MergePlan
用到的 prompt: [PJ-PLAN-STRUCTURE, PJ-PLAN-COVERAGE]
禁止:
  - 写 state
  - 给缺字段填默认值
```

所有 prompt 模板集中放在另一份 `gates.yaml`，每条给个 ID（如 `PJ-PLAN-STRUCTURE`）。Agent 代码只写"调用 ID"，不再抄 prompt 原文。

**带来的好处**：
- 改审查标准只动一个文件，不会漂移
- 新人一眼看懂每个 Agent 的边界
- "禁止清单"可以被测试自动检查（比如扫代码：`judge_agent.py` 里出现 `state.xxx = ...` 直接报错）
- 为后面三项提供"约束来源"——菜单知道能关哪些审查、流水线知道谁能并行、值班长知道什么叫"越界"

**为什么必须先做**：这是地基。后面三项都要引用说明书里的字段。

---

### O-B. 给用户一张"菜单"（Workflow Catalog）

**问题**：用户想"快速合并一个小 PR"时，现在得自己拼 `--dry-run` `--ci` `-r` 这些零散开关，还得去 YAML 里改阈值。场景和参数是一一对应的，但没人帮他做对应。

**做法**：在 `config/workflows.yaml` 里把典型场景命名好，用户选菜名就行：

```yaml
workflows:
  standard:          # 日常合并（默认）
    审查强度: 中
  migration:         # 知道是"历史迁移"场景
    审查强度: 高
    强制开启 sync-point 检测: true
  cherry-pick-only:  # 只想保留上游提交历史
    跳过: [planning, conflict_analysis]
  analysis-only:     # 不写文件，只看报告
    dry_run: true
    跳过: [auto_merge, judge_review]
```

CLI 变成：`merge <branch> --workflow migration`，替换掉现在的一堆零散 flag。

**关键细节 —— 审查强度怎么实现**：**不是**"跳过审查 Agent"，而是**调阈值**。审查 Agent 始终在岗，只是"多高的置信度才算放心"可以调：

| 档位 | 自动合并门槛 | 升级人工门槛 | 效果 |
|---|---|---|---|
| 高 | 0.95 | 0.50 | 大部分情况都走 Judge LLM 深审 / 升人工 |
| 中（默认） | 0.85 | 0.30 | 当前行为 |
| 低 | 0.70 | 0.15 | 多数情况自动通过，但 Judge 的"硬规则检查"仍执行 |

**为什么这样设计**：原本想过"low 模式直接跳过 Judge LLM 段"，但那等于在特定配置下悄悄关掉了"不确定即升级"这条核心不变量。现在只调门槛不跳 Agent，核心保障一直在。

---

### O-C. 给并行任务一套"流水线"（Parallel File Runner）

**问题**：当前遇到 5 个高风险文件要 Claude 分析时，是一个接一个排队调 LLM。墙钟时间是 5 倍单文件耗时。其实这 5 个调用互相独立，完全可以一起发出去。Executor、Judge 处理独立文件时也一样。

**做法**：写一个通用的"批量发任务"小工具，Analyst、Executor、Judge 都用它：

```
输入：一批独立文件 + 要跑的 Agent
输出：每个文件的结果（单个失败不影响其他）
```

**关键细节**：
- **并发数不写死**：有几把 API Key 就开几路，不猜 "4" 或 "8" 这种魔法数
- **自动让步**：某把 Key 被限流时，那一路暂停等待，其他继续跑
- **独立隔离**：A 文件失败不会导致 B 文件已经写好的东西被回滚

**带来的好处**：5 个高风险文件的分析耗时从 5× 降到接近 1×；而且这一套原语复用在三个 Agent 上，不是只做一个点。

---

### O-D. 给异常情况一个"值班长"（Coordinator）

**问题**：现在 Orchestrator 又要管"状态机调度"（标准活），又要管"Plan dispute 怎么办、Judge 修了两次还不过怎么办、批次太大怎么切"（判断活）。判断活散在各处，新增一种异常回环就要改 Orchestrator。

**做法**：抽一个 Coordinator 模块专门做三件"判断活"：

#### ① 异常回环的分派

"Executor 说计划不合理、要退回去"——该让 Planner 重来还是升级人工？
"Judge 修第 3 次还没过"——继续战术修还是换大局视角？

这些判断从 Orchestrator 里搬出来，集中一处。Orchestrator 回归纯粹的"状态切换"调度器。

#### ② 批次大小自己算

当前 Planner 可能一次生成"50 个文件为一批"的任务，超出模型注意力、失败一次全回滚。

Coordinator 根据"模型上下文窗口 × 利用率 ÷ 每文件平均 token"算出合理上限。用户配置只暴露一个 "想用多少上下文"（比如 60%），不填具体数字。

#### ③ "救火队长" Prompt

参考 CCGS 的"总监兜底"思路：当 Judge 反复修不过、或者 Plan dispute 连发 2 次，说明**战术层面解决不了，要跳出来看大局**。

但**不新开一个 Agent 类**——只是让现有 Planner / Judge 换一套 prompt（从 `gates.yaml` 里挑 `META-REVIEW-*` 变体），输入变成"历次失败记录 + 层依赖配置"，输出"方向性建议"。相当于同一个人换顶帽子开会，不多雇一个人。

---

## 5. 四件事的先后关系

不是按时间分期，而是按依赖顺序：

```
        第 1 步：O-A 岗位说明书
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
   第 2 步（并行）        第 2 步（并行）
   O-B 菜单              O-C 流水线
          │                   │
          └─────────┬─────────┘
                    ▼
              第 3 步：O-D 值班长
```

- **O-A 必须最先**：菜单要知道"能关哪些 prompt"、流水线要知道"谁能并行"、值班长要知道"什么算越界"——这些都得先在说明书里写清楚。
- **O-B 和 O-C 互不依赖**，可以同时推进。
- **O-D 最后**：它既要调用 O-C 的流水线（给元评审并行加载上下文），也要查 O-A 的说明书（判断越界）。

### 被明确剔除的东西

原来考虑过的"跨会话并行 Agent Teams"（多个 Claude 进程同时跑、共用一个记忆库），本方案**直接拿掉**。原因：
- 当前记忆库不保证多进程并发安全
- 多进程写文件会和现在"单一写入通道 + 快照回滚"的基本假设冲突
- 触发条件太苛刻（文件 >200 + 互不相交 + 多次迁移），实际很少命中

**要做就做全，不做半吊子占位**。等记忆库有跨进程语义了再考虑。

---

## 6. 与现有文档的关系

| 本文档引用 | 位置 |
|---|---|
| 总体架构 / 八阶段 / P1–P8 原则 | `doc/architecture.md` |
| 七个 Agent 详解 | `doc/modules/agents.md` |
| 状态机 & 状态转换 | `doc/flow.md` |
| 六类丢失模式 & 加固扫描 | `doc/multi-agent-optimization-from-merge-experience.md` |
| 迁移感知合并 | `doc/migration-aware-merge.md` |
| 其他参考项目 | `doc/references/openai-agents-python-analysis.md`、`hermes-inspired-improvements.md` 等 |

与 `openai-agents-python-analysis.md` 的互补关系：后者关注**运行时 API**（Runner / Handoff / Guardrail），本文关注**组织学与协议**——两者叠加即"机制 + 契约"双完备。

---

## 7. 不推荐照搬的部分

CCGS 的以下特性在 CMS 语境下无直接收益，**不建议移植**：

| CCGS 特性 | 不移植原因 |
|---|---|
| 39 份文档模板 | 代码合并无 GDD/叙事文档等制品 |
| Slash command 生态（72 个） | CMS 是 CLI 流水线，不是交互式 IDE |
| Hook 系统（PreToolUse / PostToolUse 等 12 个） | CMS 已有 MessageBus + Phase Hooks，不走 Claude Code 原生 hook |
| 路径域 rules | CMS `src/` 树较浅；已由 mypy strict + 单测保障 |
| Accessibility / Localization Agent 等 | 领域不重合 |

---

## 8. 结论

用一句日常语言概括方案：

> **"给每个 Agent 发一张岗位说明书，给用户一张点菜菜单，给并行任务一套流水线，给异常情况一个值班长。"**

| 方案 | 解决的问题 | 相当于 |
|---|---|---|
| **O-A 岗位说明书** | Agent 行为规则散落、prompt 内联、边界模糊 | 新人入职第一天拿到的岗位手册 |
| **O-B 菜单** | 用户要手拼一堆开关才能切场景 | 餐厅点菜单：选"日常 / 迁移 / 纯分析"即可 |
| **O-C 流水线** | 独立任务串行跑、墙钟时间线性累加 | 工厂里 N 条生产线同时开工 |
| **O-D 值班长** | 异常回环、批次大小、救火判断散在 Orchestrator 里 | 车间值班长：平时不出面，出状况时统一处理 |

四者职责不重叠，依赖顺序清晰（说明书先行 → 菜单与流水线并行 → 值班长收口），与 CMS 现有状态机完全正交：不动 Phase、不动状态转换表、不新增 Agent 类，却把 CCGS 十项组织模式以"最小结构改动"内化到 CMS。
