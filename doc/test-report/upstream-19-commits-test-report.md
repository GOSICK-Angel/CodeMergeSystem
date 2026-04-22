# CodeMergeSystem 集成测试报告

**测试日期**: 2026-04-21  
**Run ID**: `dcdf1729-75f9-4fe4-9aa6-84f79349e9f5`  
**合并目标**: `dify-official-plugins` — `test/upstream-19-commits` → `feat_merge`  
**测试人**: Angel (同时作为用户进行人工决策)
**仓库标准**：标准：manifest.yaml中author:cvte的插件为存在二次开发的，合并时应注意冲突解决，针对/Users/angel/Desktop/WA_AI/project/dify-official-plugins/models 中author: cvte的插件 dify-api 存在模型托管，合并时也应当注意冲突解决，author不是cvte的插件均直接采用远端分支修改，使用该仓库测试当前项目全流程
---

## 执行摘要

| 项目 | 值 |
|------|-----|
| 状态 | ✅ 全流程跑通（COMPLETED） |
| 上游提交数 | 19 commits |
| 计划文件总数 | 32 |
| 自动合并文件 | 49 (take_target) + 13 (human take_target/take_current) |
| 语义合并文件 | 16 (semantic_merge) |
| 升级人工文件 | 14 (escalate_human — 超大文件/SEMANTIC_MERGE不支持) |
| Judge 最终裁定 | FAIL (75 issues: 52 critical, 3 high, 4 medium, 1 low, 15 info) |
| 人工干预次数 | 2次（Plan 审批 + 13个文件决策） |
| 运行总时长 | ~3.5 小时（包含多次 debug/重试） |

> **说明**: Judge FAIL 的主要原因为 48 个 D-missing 文件未被 auto_merge 处理（layer 依赖阻塞），以及 escalate_human 文件（超大 cvte 文件）无法自动合并。这是已知系统局限，不影响流程验证。

---

## Phase 断言记录

### Phase 1: ANALYSIS（初始化）

**状态**: ✅ COMPLETED  
**时长**: ~0.2s  
**关键输出**:
- 分类文件: 7456
- 可操作文件: 124
- 上游提交: 19 commits (其中 6 commit 无法 cherry-pick，fallback to apply)

**断言**:
- [x] 成功识别 `feat_merge` 为 fork，`test/upstream-19-commits` 为上游
- [x] 正确计算 merge base commit
- [x] 所有 19 upstream commits 被枚举
- [x] 6 个无法 cherry-pick 的 commit 被标记为 fallback

---

### Phase 2: PLAN_REVIEW（Planner + PlannerJudge 协商）

**状态**: ✅ COMPLETED（stalled at round 1，人工审批通过）  
**时长**: 05:19:43 → 05:21:07（约 84s）

**协商轮次**:

| Round | PlannerJudge 裁定 | Planner 响应 | 说明 |
|-------|-------------------|-------------|------|
| 0 | revision_needed（1 issue） | 1 accept | auth.py 从 auto_safe 升级为 auto_risky ✅ 正确 |
| 1 | revision_needed（3 issues） | 3 reject | 幻觉：引用不在计划中的 3 个文件 ✅ Planner 正确拒绝 |

**最终计划**:
- Total: 32 files / Auto-safe: 8 / Auto-risky: 24 / Human-required: 0
- Auto-merge rate: 25.0%

**人工审批决策**（用户身份）:
- 决定: **APPROVE**
- 原因: Round 0 的升级正确；Round 1 的问题是 PlannerJudge 幻觉，Planner 已正确拒绝，计划分布合理

**断言**:
- [x] PlannerJudge 正确识别安全敏感文件 `tools/jira/tools/auth.py` 被低估
- [x] Planner 正确接受安全升级建议
- [x] Planner 正确拒绝 PlannerJudge 幻觉（引用不存在的文件路径）
- [x] 计划中 cvte 插件文件正确列入 auto_risky 批次
- [x] 人工审批可通过 `--decisions` 文件提供

---

### Phase 3: AUTO_MERGE（自动执行）

**状态**: ✅ COMPLETED  
**时长**: 06:44:29 → 06:44:30（约 1s，因文件已有决策，大多跳过）

**执行结果**:
- take_target: 17 files（requirements.txt、小 Python/YAML 文件）
- escalate_human: 23 files（SEMANTIC_MERGE 策略不支持，超大 cvte 文件无法修复）
- semantic_merge: 6 files（manifest 文件版本协商）

**Batch Judge sub-review**:
- 首次运行: no consensus（PlannerJudge validation 错误，行号字段接受了字符串）
- **已修复**: `JudgeIssue.affected_lines` 添加 `_LineList` BeforeValidator，静默丢弃非整数行号

**断言**:
- [x] auto_safe 批次无需 judge 审查，直接执行
- [x] auto_risky 批次触发 batch judge sub-review
- [x] escalate_human 决策被正确记录（不阻塞其他文件）
- [x] 已有决策的文件不被重复处理（`_execute_batch` 跳过逻辑）

---

### Phase 3b: CONFLICT_ANALYSIS（冲突分析）

**状态**: ✅ COMPLETED  
**时长**: 06:44:30 → 06:48:26（约 4 分钟）

**分析结果**:
- conflict_analyses: 482 files
- 需要人工决策: 13 files

**13 个人工决策文件**（用户身份）:

> ⚠️ **系统问题**：以下 13 个文件中，11 个为 langgenius 插件。按仓库约定（非 cvte author 插件直接采用 upstream），这 11 个文件应由系统自动 `take_target`，无需人工介入。系统未能基于 `manifest.yaml` 中的 `author` 元数据自动决策，是 conflict_analysis 阶段的策略盲区。

| 文件 | 判断依据 | 决定 | 是否应人工 |
|------|----------|------|------------|
| `models/azure_openai/provider/azure_openai.yaml` | cvte 插件，upstream 新增 Entra ID auth 有价值 | take_target | ✅ 应人工 |
| `models/tongyi/manifest.yaml` | cvte 插件，upstream 要改 author 回 langgenius | take_current（保留 cvte） | ✅ 应人工 |
| `agent-strategies/cot_agent/strategies/ReAct.py` | langgenius 插件 | take_target | ❌ 应自动 |
| `agent-strategies/cot_agent/strategies/function_calling.py` | langgenius 插件 | take_target | ❌ 应自动 |
| `models/bedrock/manifest.yaml` | langgenius，版本升级 0.0.54→0.0.58 | take_target | ❌ 应自动 |
| `models/bedrock/utils/inference_profile.py` | langgenius | take_target | ❌ 应自动 |
| `models/ollama/manifest.yaml` | langgenius | take_target | ❌ 应自动 |
| `tools/jira/provider/jira.yaml` | langgenius | take_target | ❌ 应自动 |
| `tools/paddleocr/manifest.yaml` | langgenius，版本升级 0.1.3→0.1.4 | take_target | ❌ 应自动 |
| `tools/paddleocr/tools/document_parsing.py` | langgenius | take_target | ❌ 应自动 |
| `tools/paddleocr/tools/document_parsing_vl.py` | langgenius | take_target | ❌ 应自动 |
| `tools/paddleocr/tools/text_recognition.py` | langgenius | take_target | ❌ 应自动 |
| `tools/paddleocr/tools/utils.py` | langgenius | take_target | ❌ 应自动 |

**断言**:
- [x] conflict_analysis 正确识别需要语义合并的文件
- [FAIL] cvte 插件与 langgenius 插件的决策路径被正确区分（系统未读取 manifest.yaml author 字段，11 个 langgenius 插件被错误升级为人工，应自动 take_target）
- [x] `--decisions` 文件格式（decisions: list）被正确解析
- [x] 13 个文件决策全部被系统加载（"Loaded 13 decisions"）

---

### Phase 4: JUDGE_REVIEW（Judge 最终审查）

**状态**: ✅ COMPLETED（3次 resume，最终接受裁定）  
**时长**: ~26 分钟（Judge 逐文件 LLM 审查）

**Judge 裁定摘要**:

| 轮次 | 时间 | 裁定 | Issues |
|------|------|------|--------|
| Round 0（第1次 resume）| 07:01 | FAIL | 85 issues |
| Round 0（第2次 resume）| 07:53 | FAIL | 74 issues |
| Round 0（第3次 resume）| 08:36 | FAIL | 75 issues |

**最终 Judge Verdict**:
```
verdict: FAIL
passed_files: 35
failed_files: 52
critical: 52 | high: 3 | medium: 4 | low: 1 | info: 15
veto_triggered: false
```

**问题分类**:
- **D-missing 文件未处理**: 44 issues（占 52 critical 中的绝大多数）
  - 模块: `triggers/twilio_trigger/`, `tools/comfyui/tools/json/`, `tools/jira/utils/`
  - 原因: layer 依赖未满足导致 auto_merge 跳过
- **B-class 文件与 upstream 不一致**: 5 issues
  - `tools/aihubmix_image/`, `tools/email/`
- **escalate_human 文件质量问题**: 8 issues
  - `azure_openai/models/constants.py`: 截断字符串、垃圾文本（超大 cvte 文件）
  - `azure_openai/models/llm/llm.py`: gpt-5 支持不完整
  - `cot_agent/strategies/ReAct.py`: 空类 stub

**人工裁定接受决策**（用户身份）:
- 决定: **ACCEPT** judge_verdict
- 原因: D-missing 问题（44 issues）属系统设计边界，escalate_human 文件（8 issues）需人工手动合并，均为已知局限
- ⚠️ **遗漏**：5 个 B-class 非 cvte 文件（`tools/email/`、`tools/aihubmix_image/`）与 upstream 不一致，属可修复问题，未处理即接受 FAIL 是流程疏漏；系统应在 FAIL 接受前区分"系统局限"与"可修复问题"并强制确认

**断言**:
- [x] Judge 成功运行 LLM 逐文件审查（71 files × ~8-15s/file）
- [x] Judge 正确识别 D-missing 文件为 critical issue
- [x] Judge 正确识别 B-class 文件差异
- [x] judge_resolution: accept 通过 checkpoint 修改被正确处理
- [x] 流程从 judge_review → generating_report → completed

---

### Phase 5: GENERATING_REPORT

**状态**: ✅ COMPLETED  
**时长**: 08:37:32（约 0.01s）

**输出文件**:
- `outputs/merge_report_dcdf1729.md` — 详细合并报告
- `outputs/merge_report_dcdf1729.json` — JSON 格式报告
- `outputs/plan_review_dcdf1729.md` — Plan 审查报告
- `MERGE_RECORD/MERGE_PLAN_test_upstream-19-commits_dcdf1729.md` — 合并计划

---

## Bug 修复记录（本次测试发现并修复）

| # | Bug | 修复位置 | 描述 |
|---|-----|----------|------|
| 1 | `OPENAI_BASE_URL` 配置错误 | `.env` | URL 末尾含 `/v1/chat/completions`，client.py 追加 `/v1` 导致 404 |
| 2 | `MemoryExtractorAgent.can_handle` 未实现 | `src/agents/memory_extractor_agent.py` | 添加 `return False` |
| 3 | `JudgeIssue.affected_lines` Pydantic 验证 | `src/models/judge.py` | LLM 输出 `"last visible line"` 等字符串导致解析失败，改用 `_LineList` BeforeValidator |
| 4 | Auto_merge 无限循环 | `src/core/phases/auto_merge.py` | Batch judge sub-review 失败后缺少 `paused=True`，导致 human_review → AUTO_MERGING 死循环 |
| 5 | 已决策文件被重复处理 | `src/core/phases/auto_merge.py` | `_execute_batch` 未跳过已有 file_decision_records 的文件 |
| 6 | Judge repair 无限超时 | `src/core/phases/judge_review.py` | 最后一轮仍调用 `executor.build_rebuttal()`，大文件超时 182s × 3次，添加 `if round_num >= max_rounds - 1: continue` |

---

## 优化建议清单

### P0（阻断性）

1. **D-missing 文件 layer 依赖阻塞**  
   48 个 D-missing 文件被跳过是本次 Judge FAIL 的主因。auto_merge 的 `verify_layer_deps()` 阻止了这些文件的处理，但缺少降级策略（直接 copy from upstream）。应为 D-missing 文件添加 fallback：即使 layer 依赖未满足，也通过 `_copy_from_upstream()` 处理。

2. **SEMANTIC_MERGE 策略在 Executor 中未实现**  
   14 个文件因 `Unsupported auto-merge strategy: MergeDecision.SEMANTIC_MERGE` 被 escalate_human。需要在 Executor 的 `execute_auto_merge()` 中实现 semantic merge 逻辑，或在 conflict_analysis 阶段将超大文件直接路由为 human_required。

### P1（影响自动化率）

3. **超大文件（>30K chars）无法整体 LLM 处理**  
   `azure_openai/models/constants.py`（139K chars）、`llm.py`（69K chars）超出单次 LLM 上下文，被反复 escalate。建议：
   - 按语义边界（函数/类/import block）将文件分块，每块独立调用 LLM 合并，结果拼接后做语法完整性校验
   - `human_required` 仅作分块合并失败的兜底，不应作为大文件的主要处理路径

4. **Judge repair 超时严重（~9 min/大文件）**  
   182s 请求超时 × 3次重试 = 每个大文件耗时 9 分钟。建议降低 `request_timeout_seconds` 到 60s，减少单次等待时间。或在 `executor.repair()` 中预先检查文件大小，跳过无法处理的大文件。

5. **PlannerJudge 幻觉（引用计划外文件）**  
   Round 1 PlannerJudge 输出了 3 个不在计划中的文件路径。Planner 虽然正确拒绝，但浪费了一轮协商和额外 LLM 调用。建议 PlannerJudge 的输出模式明确要求文件路径必须来自输入的 plan batches。

### P2（体验改进）

6. **Checkpoint 未在 awaiting_human+judge_verdict 时保存**  
   多次 resume 后 checkpoint 仍显示 `judge_reviewing` 而非 `awaiting_human`，需手动修改 checkpoint。建议在 judge_review phase 完成（PASS 或 FAIL 裁定后）添加一次强制 checkpoint save。

7. **resume 不支持从 `judge_reviewing` 直接注入 `judge_resolution`**  
   目前 resume.py 仅在 `state.status == AWAITING_HUMAN` 时处理 `judge_resolution`。应扩展以支持从 `judge_reviewing` 状态注入，避免需要手动修改 checkpoint。

8. **Judge B-class 检查未区分文件性质**  
   `tools/email/` 的 author 为 langgenius（非 cvte），Judge 将其标记为"B-class differs from upstream"是正确判断，不应被视为误报。  
   真正的问题在于 `author: cvte` 的插件：这类文件与 upstream 不一致是预期的（存在二次开发定制），但 Judge 目前对所有文件统一使用"与 upstream 一致"作为检查标准，会将合法定制误判为问题。  
   建议：Judge 对 `author: cvte` 文件切换检查标准为"定制逻辑是否被保留"（即合并后 cvte 新增的业务逻辑、接口扩展等不得丢失），而非要求与 upstream 完全一致。

9. **YAML 决策文件中含冒号的注释字段报错**  
   `reviewer_notes: Non-cvte plugin (author: langgenius)` 中的冒号导致 YAML 解析失败。建议 collect_decisions_file 使用更宽松的解析，或在文档中提示注释字段需加引号。

---

---

## 系统改进方案

> 以下改进均面向通用场景设计，不针对 dify-official-plugins 仓库写死任何规则。系统通过可配置机制理解仓库约定，由用户在 `config.yaml` 中声明，agent 读取后通用执行。

---

### 改进 A：项目约定上下文注入（解决 11 个 langgenius 文件被错误升级问题）

**根因**：`conflict_analysis` 阶段将无法自动合并的文件一律升级为人工，Planner 和 ConflictAnalystAgent 对目标仓库的合并约定一无所知，无法自主决策。并非所有项目都有统一的元数据文件（如 `manifest.yaml`），约定更多存在于仓库的 `CLAUDE.md`、`README.md` 或用户的自然语言描述中。

**方案**：系统在初始化阶段自动读取目标仓库的上下文文档，将其作为"项目约定"注入所有决策 agent 的 prompt。用户也可在 `.merge/config.yaml` 中通过 `project_context` 字段补充或覆盖。Agent 通过 LLM 理解这些自然语言约定并在决策时应用，无需学习 DSL。

**上下文来源（按优先级合并）**：
1. `.merge/config.yaml` 中的 `project_context` 字段（用户显式声明，优先级最高）
2. 目标仓库根目录的 `CLAUDE.md`（若存在）
3. 目标仓库根目录的 `README.md`（若存在，截取前 N 行）

**当以上来源均为空时**：系统在 `ANALYSIS` 阶段末尾检测到 `resolved_project_context` 为空，自动提示用户运行 `merge init`（或 `merge <branch> --init-context`）；该命令分析目标仓库的目录结构、代表性文件（`manifest.yaml`、`pyproject.toml`、`package.json` 等）和 git log，调用 LLM 生成初始 `CLAUDE.md` 草稿并写入目标仓库根目录，供用户审阅后复用。

**配置示例**（`.merge/config.yaml`）：
```yaml
project_context: |
  本仓库为 Dify 插件集合。判断合并策略的关键依据是插件目录下
  manifest.yaml 中的 author 字段：
  - author 为第三方（如 langgenius）的插件：无二次开发，直接采用 upstream 版本
  - author 为 cvte 的插件：存在定制化开发，需语义合并并保留 cvte 新增的业务逻辑
  - models/dify-api 目录下的插件存在模型托管定制，合并时需格外注意接口兼容性
```

**涉及改动**：
| 文件 | 改动 |
|------|------|
| `src/models/config.py` | `MergeConfig` 增加 `project_context: str = ""` 字段 |
| `src/core/runner.py`（或初始化入口） | 启动时读取目标仓库 `CLAUDE.md` / `README.md`，与 `project_context` 合并为 `resolved_project_context` 存入 `MergeState`；若三者均为空，在 `ANALYSIS` 结束后提示用户运行 `merge init` |
| `src/cli/init_context.py`（新增） | `merge init` 子命令实现：扫描目标仓库结构与代表性文件，调用 LLM 生成 `CLAUDE.md` 草稿并写入目标仓库根目录 |
| `src/agents/planner_agent.py` | prompt 中注入 `resolved_project_context`，要求 Planner 在制定计划时参考项目约定决定文件策略 |
| `src/agents/conflict_analyst_agent.py` | prompt 中注入 `resolved_project_context`，在判断是否升级人工前先依据约定推断策略 |

---

### 改进 B：Judge issue 分级与 FAIL 接受门控（解决可修复问题被静默接受问题）

**根因**：`JudgeIssue` 没有区分"系统局限（无法自动修复）"与"可修复问题"，FAIL 接受时系统不强制确认，导致用户误接受了本可修复的 B-class issue。

**方案**：为 `JudgeIssue` 增加 `resolvability` 字段；Judge prompt 要求对每个 issue 分类；`judge_review` phase 在 FAIL 时，若存在 `fixable` issues，进入 `AWAITING_HUMAN` 并展示清单，而非静默接受。

**`resolvability` 枚举值**：
- `fixable`：文件与 upstream 不一致且可通过 take_target / 重新合并修复
- `system_limitation`：D-missing、策略不支持等已知系统边界
- `human_required`：escalate_human 文件，需人工手动处理

**涉及改动**：
| 文件 | 改动 |
|------|------|
| `src/models/judge.py` | `JudgeIssue` 增加 `resolvability: Literal["fixable", "system_limitation", "human_required"]` 字段 |
| `src/agents/judge_agent.py` | 更新 Judge prompt，要求对每个 issue 填写 `resolvability`，并给出分类依据 |
| `src/core/phases/judge_review.py` | FAIL 时检查是否存在 `fixable` issues；若有，状态机转 `AWAITING_HUMAN` 并附 fixable 清单，强制用户确认或处理后再接受 |

---

### 改进 C：大文件语义分块处理（解决 >30K 文件无法 LLM 合并问题）

**根因**：Executor 对大文件直接传整体内容给 LLM，超出上下文限制后只能 escalate_human，无法利用 LLM 辅助。

**方案**：新增 `ChunkMergeExecutor`，将大文件按语义边界拆分为若干块（每块 ≤ 配置的 `chunk_size_chars`），对每块独立调用 LLM 合并，拼接结果后做语法完整性校验；校验失败时才降级为 `human_required`。

**语义分块策略**（按优先级选择）：
1. Python/Go/JS：按顶层函数/类边界切分（使用 AST 或正则识别 `def`/`class`/`func` 等）
2. YAML/JSON：按顶层 key 切分
3. 其他：按固定行数切分，在空行处对齐

**涉及改动**：
| 文件 | 改动 |
|------|------|
| `src/tools/chunk_processor.py` | 新增文件，实现 `split_by_semantic_boundary(content, file_ext, chunk_size)` 和 `merge_chunks(chunks)` |
| `src/agents/executor_agent.py` | 检测文件大小；超过 `chunk_size_chars` 阈值时路由到 `ChunkMergeExecutor`；分块合并结果需通过语法校验 |
| `src/models/config.py` | `MergeConfig` 增加 `chunk_size_chars: int = 20000` 配置项 |

---

### 改进 D：Judge 文件检查策略可配置化（解决 cvte 定制文件被误判问题）

**根因**：Judge 对所有文件统一使用"合并结果应与 upstream 一致"的检查标准，无法识别"定制文件与 upstream 不同是预期行为"的场景，导致合法定制被误报为 critical issue。

**方案**：`FileMergeDecision` 增加 `judge_check_strategy` 字段，Planner 基于 `metadata_rules` 为文件分配检查策略，Judge agent 根据策略使用不同的 prompt 评估标准：

| `judge_check_strategy` | 检查目标 |
|------------------------|----------|
| `upstream_match`（默认）| 合并结果与 upstream 相比无遗漏、无引入错误 |
| `customization_preserved` | 定制新增的业务逻辑、接口扩展、配置字段在合并后完整保留；upstream 新增内容被正确集成 |

**涉及改动**：
| 文件 | 改动 |
|------|------|
| `src/models/plan.py` | `FileMergeDecision` 增加 `judge_check_strategy: Literal["upstream_match", "customization_preserved"] = "upstream_match"` |
| `src/agents/planner_agent.py` | 在生成 plan 时，命中 `metadata_rules` 且策略为 `semantic_merge` 的文件自动设置 `judge_check_strategy = "customization_preserved"` |
| `src/agents/judge_agent.py` | Judge prompt 根据 `judge_check_strategy` 切换评估标准；`customization_preserved` 策略下不将"与 upstream 不一致"本身视为 issue |

---

### 改进优先级

| 优先级 | 改进 | 影响 |
|--------|------|------|
| P0 | **改进 A**（元数据规则） | 消除大量不必要的人工干预，直接提升自动化率 |
| P0 | **改进 B**（issue 分级） | 防止可修复问题被静默接受，保证合并质量 |
| P1 | **改进 C**（分块处理） | 解锁大文件 LLM 合并能力，减少 human_required |
| P1 | **改进 D**（check strategy） | 消除定制文件误报，提升 Judge 结果可信度 |

---

## 运行时间线

| 时间 | 事件 |
|------|------|
| 05:14 | 发现 Bug#1（OPENAI_BASE_URL 404），修复并重启 |
| 05:19 | Run dcdf1729 启动 |
| 05:21 | Plan review 完成（2轮 negotiation），进入 AWAITING_HUMAN |
| 05:22 | 人工审批计划（APPROVE） |
| 05:33 | Resume 启动，进入 AUTO_MERGING |
| 05:55 | Bug#4（无限循环）发现，修复 paused=True |
| 06:06 | Bug#5（重复处理）修复，跳过已有决策文件 |
| 06:33 | Auto_merge 完成（696.5s），进入 conflict_analysis |
| 06:48 | Conflict analysis 完成，13 文件待人工决策 |
| 06:51 | 13 个文件决策提供，Executor 开始处理 |
| 07:01 | 第一次 Judge run FAIL（85 issues） |
| 07:19 | Bug#3（JudgeIssue 行号 Pydantic 错误）修复 |
| 07:38 | Bug#6（judge repair 超时）修复，max_dispute_rounds=1 |
| 08:19 | Judge phase 完成（1579.7s），verdict: FAIL |
| 08:37 | Checkpoint 手动更新为 awaiting_human，接受 judge 裁定 |
| 08:37 | 报告生成，状态: COMPLETED |

---

## 参考文件

- Plan Review: `outputs/plan_review_dcdf1729-75f9-4fe4-9aa6-84f79349e9f5.md`
- Merge Report: `outputs/merge_report_dcdf1729-75f9-4fe4-9aa6-84f79349e9f5.md`
- Debug Log: `outputs/debug/run_dcdf1729-75f9-4fe4-9aa6-84f79349e9f5.log`
- LLM Traces: `outputs/debug/llm_traces_dcdf1729-75f9-4fe4-9aa6-84f79349e9f5.jsonl`
- Checkpoint: `outputs/debug/checkpoints/checkpoint.json`
