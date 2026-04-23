# CodeMergeSystem 集成测试报告 — upstream-51-commits

**测试日期**：2026-04-22 → 2026-04-23
**Run ID**：`8c02eb83-a98e-4936-b12f-0c1620f296a5`
**合并目标**：`dify-official-plugins` 的 `test/upstream-51-commits` → `feat_merge`
**测试人**：Angel（同时担任人工决策者）
**仓库规则**：`manifest.yaml` 中 `author: cvte` 的插件为二次开发插件，需谨慎冲突解决；`/models` 下 CVTE 插件存在 dify-api 模型托管；非 CVTE 插件直接采纳上游。

---

## 执行摘要

| 指标 | 值 |
|------|-----|
| 上游提交数 | **97 commits** |
| 分类文件 | 8095（其中 784 可操作） |
| Cherry-pick 成功 | **7 / 13**（54% 成功，保留 git 历史） |
| AUTO_MERGE 文件 | 492 files（commit `a12455ba`） |
| CONFLICT_ANALYSIS 规则解析 | 166 files（commit `78e78cb0`） |
| HUMAN_REVIEW 决策 | 20 files（commit `e803fdfc`） |
| 最终状态 | ⚠️ **judge_review 无法收敛（进入循环 bug）** |
| JudgeVerdict | **428 issues**（26 critical + 173 high + 162 medium + 35 low + 32 info） |
| Judge Meta-Review | FAIL：提示"pervasive repo-wide quality and correctness regressions" |
| 总 LLM 调用 | **990+**（含 Judge 循环重跑） |
| 总耗时至手动终止 | ~6h 45min |
| 确认成本（含首轮 judge） | ≈ $10.93+（仅到首次 FAIL 前的可统计部分） |

---

## Phase 断言记录

### Phase 1 — INITIALIZE

**状态**：✅ COMPLETED（82.1s）
**起止**：21:54:50 → 21:56:12

**关键输出**：
- 三向分类 8095 文件 → 可操作 784
- 上游 97 commits 全部枚举
- Commit Replay 分类：**13 replayable / 84 non-replayable**（相较 upstream-46 的 0/46，已有显著提升）
- Interface Changes：已提取（用于反向影响分析）

**断言**：
- [x] 正确识别 `feat_merge` 为 fork，`test/upstream-51-commits` 为上游
- [x] 计算 merge base，可操作文件数合理
- [x] Commit Replayer 的 B/D_MISSING 分类机制生效
- [x] Reverse-impact scanner 完成接口变更提取

---

### Phase 2 — PLAN_REVIEW

**状态**：✅ COMPLETED（5.0s，**Round 0 一次通过**）
**起止**：21:56:15 → 21:56:21

**PlannerJudge**（provider=`openai`, model=`gpt-5.4`）：
- Round 0 verdict: **approved (0 issues)**
- 说明原文："No concrete misclassifications found under the provided review rules. High-risk and security-adjacent files shown are already classified at least auto_risky."
- 成本：**1 call / $0.12258**

**对比 upstream-46**：46 次测试 PlannerJudge 遭遇 `gpt-5.1 model not supported` 代理兼容性错误，触发全量升级 HUMAN_REVIEW；本次 `gpt-5.4` 代理路由正常，恢复了 PlannerJudge 的自动快速通道。

**断言**：
- [x] gpt-5.4 代理兼容性修复，PlannerJudge 可用
- [x] 0 issues 通过后不再触发 plan human review（无 HUMAN_REQUIRED 文件时跳过 AWAITING_HUMAN）
- [x] decisions 文件未消费（自动放行）

---

### Phase 3 — Cherry-pick / Commit Replay

**状态**：⚠️ **7/13 成功（54%）**
**起止**：21:56:21 → 21:56:23

**结果明细**：

| SHA | Commit | 文件数 | 结果 |
|-----|--------|-------|------|
| `1de7b0d4` | fix: fix miss package (#2421) | 2 | ✅ |
| `07295ac6` | feat: add more voyage models (#2419) | 13 | ✅ |
| `337f114e` | feat: support single tenant (#2448) | 3 | ✅ |
| `04868b07` | chore: check packaging before uv sync (#2470) | — | ❌ |
| `843176f3` | fix: replace existing reference to brew (#2481) | — | ❌ |
| `11a737ec` | chore: package plugin before uv sync (#2482) | — | ❌ |
| `170aba7b` | chore: allow fork PR to read secret (#2486) | — | ❌ |
| `0d2e6a3f` | fix: export Dify CLI to PATH in CI (#2491) | — | ❌ |
| `8fb3a113` | fix(models/anthropic): remove deprecated models (#2489) | — | ❌ |
| `c19775f2` | feat: add Plivo SMS tool plugin (#2502) | 14 | ✅ |
| `ad5d669a` | feat(models/moonshot): add kimi-k2.5 (#2498) | 3 | ✅ |
| `68189a7c` | feat(tools): add Seltz AI-powered search (#2500) | 17 | ✅ |
| `cd8502ef` | Feat：somark plugins (#2487) | 19 | ✅ |

**断言**：
- [x] Cherry-pick 成功的 commit 保留了原作者、message、SHA 链
- [ ] **46% 失败率过高**：所有失败集中于 `.github/workflows/`（pure B category 文件）和 `models/anthropic/`，说明纯类别前过滤之后仍遇到 git 层面的 apply 冲突（见 O-R3）

---

### Phase 4 — AUTO_MERGE

**状态**：✅ COMPLETED（1909.1s ≈ 31.8 min）
**起止**：21:56:23 → 22:28:10
**commit**：`a12455ba merge(auto_merge): resolve 492 files`

**执行摘要**：
- Judge 批次：Layer 0 → Layer 9，使用 `gpt-5.4`
- 总 LLM 调用：**67**（judge 61 + planner_judge 1 + executor 5）
- 成本：**$7.45**
- 批次平均延迟：~25s
- 提示 token 利用率：**0.2%–0.7%**（max_tokens=8192 时输出普遍仅 1-2K tokens）
- Coordinator 批次拆分：`225 files → 4 sub-batches`、`247 files → 5 sub-batches`（max_size=60），正常
- Layer 3（models_extensions）与 Layer 8（tests）因依赖未就绪被阻塞 — 产生 9 个 `d_missing_not_processed` critical issue

**对比 upstream-46**：
- 本次 67 calls vs upstream-46 第三次运行 33 calls（判词语 risky 降到 257）。**整体效率显著改善**（仅单次 AUTO_MERGE 而非三次）。

**断言**：
- [x] Judge 对 auto_safe 确定性处理（无 LLM）；对 risky 文件批次审查
- [x] Executor 能并发应用变更
- [x] max_dispute_rounds=1 未被触发（Layer 1 一次通过）
- [ ] **Layer 3/8 依赖阻塞导致 D-missing 文件漏处理**（见 O-D1）

---

### Phase 5 — CONFLICT_ANALYSIS

**状态**：✅ COMPLETED（2841.9s ≈ 47.4 min）
**起止**：22:28:10 → 23:15:33
**commit**：`78e78cb0 merge(conflict_resolution): resolve 166 files`

**执行摘要**：
- Commit-stream：44 commits → 11 rounds（827 files）
- 规则解析：大量 `whitespace_only`、`line_addition_union` 直接处理（明显多于 upstream-46 的 63）
- Conflict Analyst（`claude-haiku-4-5-20251001`）：8 calls / $0.14
- 成功 LLM 5 次；失败 3 次（原因见下）
- 最终 712 个 Strategy decisions 记录
- 其中 CVTE（tongyi）插件的 `.py` 文件被正确标记 `escalate_human`；非 CVTE 插件均 `take_target`

**⚠️ 严重错误**（触发 3 次 commit-round LLM 全失败）：

| 时间 | 错误类别 | 影响范围 |
|------|---------|---------|
| 22:47:56 | `'ThinkingBlock' object has no attribute 'text'` | 7 files / 1 commit |
| 22:58:19 | `'utf-8' codec can't encode character '\udc89'` | **446 files / 5 commits** |
| 23:00:29 | `'utf-8' codec can't encode character '\udc89'` | 12 files / 5 commits |

两类 bug 都是通用代码缺陷：
1. **ThinkingBlock 解析缺失**：Anthropic 响应包含 thinking block 时，`.text` 属性访问失败（见 O-B1）
2. **UTF-8 代理对编码崩溃**：上游文件含 `\udc89` 等 Unicode surrogate pair 时，整个请求 payload 序列化失败，无法重试（见 O-B2）

**断言**：
- [x] 规则解析器处理明确冲突有效
- [x] LLM 失败时规则解析器兜底，不整体崩溃
- [x] CVTE/非 CVTE 策略路由符合规则
- [ ] 两类严重 bug 导致 465 文件的 commit-stream 失败，降级到规则解析（见 O-B1/O-B2）

---

### Phase 6 — HUMAN_REVIEW（第一次进入 AWAITING_HUMAN）

**状态**：✅ COMPLETED（Executor 写入 20 文件）
**起止**：23:15:33 AWAITING_HUMAN → 23:45:40 commit `e803fdfc`

**pending 列表**：20 个文件需人工决策（仅 tongyi 为 CVTE）

#### 人工决策（用户身份）

| 文件 | 决策 | 类型 | 理由 |
|------|------|------|------|
| `models/tongyi/.difyignore` | `take_current` | CVTE | 保留 CVTE 专属打包忽略规则 |
| `models/tongyi/models/llm/llm.py` | `semantic_merge` | CVTE | 上游 +39 / fork -129，dify-api 模型托管需保留 |
| `models/tongyi/models/rerank/rerank.py` | `semantic_merge` | CVTE | CVTE 定制 |
| `models/tongyi/models/speech2text/speech2text.py` | `semantic_merge` | CVTE | CVTE 定制 |
| `models/tongyi/models/text_embedding/text_embedding.py` | `semantic_merge` | CVTE | CVTE 定制 |
| `models/tongyi/models/tts/tts.py` | `semantic_merge` | CVTE | CVTE 定制 |
| `agent-strategies/cot_agent/manifest.yaml` | `take_target` | langgenius | 非 CVTE |
| `agent-strategies/cot_agent/prompt/template.py` | `take_target` | langgenius | 非 CVTE |
| `tools/jira/tools/get_recent_projects.{py,yaml}` | `take_target` ×2 | langgenius | 非 CVTE |
| `tools/paddleocr/*` | `take_target` ×7 | langgenius | 非 CVTE |
| `models/ollama/_assets/ollama_rerank.png` | `take_target` | langgenius | 非 CVTE |
| `models/bedrock/manifest.yaml` | `take_target` | langgenius | 非 CVTE |
| `models/jina/manifest.yaml` | `take_target` | langgenius | 非 CVTE |
| `tools/general_chunk/manifest.yaml` | `take_target` | langgenius | 非 CVTE |

**Resume 命令**：
```bash
merge resume --run-id 8c02eb83... --decisions /tmp/merge-upstream-51-decisions.yaml
```
- 20 decisions 全部加载成功
- Executor 执行后 commit `e803fdfc`

---

### Phase 7 — JUDGE_REVIEW

**状态**：⚠️ **未收敛，系统进入循环 bug**
**起止**：23:45:40 → 03:45:37（**14826.3s ≈ 4h7m**）

**Round 0**（00:48:03 前）：
- 对 739 files 逐文件 Judge LLM 调用
- ~420 次 LLM calls
- verdict：**non-PASS**

**Round 1 Dispute**（00:49:39 – 03:45:33）：
- Executor 接受所有 issues，修复 **308 items**
- Executor 短 prompt（~300-400 tokens）快速修复后，大文件 repair 出现 `Skipping LLM repair for oversized file models/volcengine_maas/models/llm/llm.py (current=50470 chars, limit=30000)`（O-P1）
- Judge re-review 所有 739 files
- verdict：**non-PASS（428 fixable issues）**

**Coordinator 介入**：
- `judge stalled after 2 rounds (threshold=2) → meta_review`
- Judge meta-review 输出：
  > "The branch is blocked by pervasive, repo-wide quality and correctness regressions that are too numerous for incremental fixes to converge to a PASS."
  > "Stop patching round-by-round; narrow scope or rebase to a known-good baseline, then fix issues in prioritized batches with automated checks."

**⚠️ 系统 Loop Bug**（见 O-L1）：
- Meta-review 完成后，`judge_review` phase 返回 `AWAITING_HUMAN`
- `human_review` Case 0（`judge_resolution is not None` 检查）未命中（因为用户未提供 resolution）
- `human_review` Case 1（`if state.human_decision_requests` 有值）被匹配
- Case 1 走 "not pending" 分支（20 个 CVTE decisions 已全部填充）→ 盲目 transition 回 `JUDGE_REVIEWING`
- Judge 再次从 Round 0 开始重审所有 739 files（再消耗 +100+ 次 LLM 调用）→ 若继续不 PASS，又会循环
- 第二轮 judge_review 运行 ~50 分钟（99 calls）后仍未结束 —— 被手动终止

#### 最终 JudgeVerdict（Round 1 结果）

| 项 | 值 |
|----|-----|
| 总 issues | **428**（全部 `fixable`） |
| Critical | 26 |
| High | 173 |
| Medium | 162 |
| Low | 35 |
| Info | 32 |

**Top 5 issue_type**：
| 类型 | 数量 |
|------|-----|
| `wrong_merge` | 221 |
| `other` | 134 |
| `missing_logic` | 49 |
| `syntax_error` | 15 |
| `d_missing_not_processed` | 9 |

**典型 critical issue**（示例）：
```
file_path: models/mimo/_assets/icon_s_en.png
issue_level: critical
issue_type: d_missing_not_processed
description: D-missing file was never processed by auto_merge
             (likely blocked by unmet layer dependencies)
veto_condition: D-missing file not processed by auto_merge
```

**Summary 节选**：
> "The merge result is not acceptable. It has numerous blocking problems, including multiple missing files that were never processed, several syntactically invalid or truncated Python source files, and many cases where upstream-only changes were not reliably adopted or where /models merge policy may have dropped required fork-specific logic."

---

## 记忆系统输入与利用

### 输入来源

1. **Initialization-derived memory**：
   - Phase `initialize`: 24 entries created
   - Phase `planning`: +3 new = 24 total
   - Phase `auto_merge`: +9 new, -3 superseded = 30 total
   - Phase `conflict_analysis`: +6 new = 36 total
   - Phase `judge_review`: 0 new / 0 superseded = 36 total（**judge 阶段记忆贡献为零**）

2. **Memory extractor LLM**：本次未被显式调用（`by_agent` 统计无 memory_extractor 项）

### 利用情况（观测）

- Planner / Judge 的 prompt 中都通过 `ContextBuilder` 注入记忆条目
- 第二次 judge_review 重启时，记忆应提供"上一轮已拒绝"的先验，但实际 Round 0 的 428 issues 几乎与首轮一致 —— 说明**记忆未有效抑制重复判定**（见 O-M1）

### 问题

- 跨 phase memory 只在 phase 边界更新（`Memory updated after <phase>`），dispute 循环内部不更新
- judge_review 跨 dispute round 时，上一轮 428 issues 与 Executor 修复记录未被喂回 Judge 作为显式记忆 → Judge 不知道哪些已修复、哪些是"新发现"
- `memory_extractor` agent 被定义（haiku-4-5）但未触发，可能因为未达到 trigger 阈值（见 O-M2）

---

## Agent LLM 上下文压缩情况

### Staged Processing 事件

- **触发次数**：26 次（都发生在 judge_review 阶段）
- **压缩示例**（摘自日志）：

| 文件 | 总 chunks | full | signature | drop | 最终 tokens |
|------|----------|------|-----------|------|------------|
| `models/gemini/models/llm/llm.py` | 178 | 55 | 59 | 33 | 6,415 / 823,689 |
| `models/tongyi/models/llm/llm.py` | 78 | 18 | 18 | 12 | 6,387 / 823,691 |
| `models/tongyi/models/text_embedding/text_embedding.py` | 54 | 3 | 9 | 22 | **312 / 823,691** |
| `models/minimax/models/llm/llm.py` | 39 | 2 | 3 | 22 | 356 / 823,690 |
| `models/volcengine_maas/models/llm/models.py` | 15 | 4 | 4 | 3 | 4,556 / 823,691 |

**核心指标**：
- 总输入 token budget：**823,691**
- 典型实际使用：**312 – 6,415 tokens**（利用率 < 1%）
- Relevance 评分的 `drop` 列占比高（22/54 = 41%）→ 说明 compressor 积极剔除不相关 chunks

### Prompt Cache 利用

| 指标 | 值 |
|------|-----|
| `cache_read` | **0** |
| `cache_write` | **0** |
| 结果 | **缓存完全未命中 / 未写入** |

原因分析：
- `cache_strategy: system_and_recent` 在 config 中已配置
- 但 `gpt-5.4` 走 OpenAI provider，而 prompt caching 仅 Anthropic 支持（`AgentLLMConfig.cache_strategy` 的 docstring 明确说 "Ignored for OpenAI providers"）
- 实际使用 Anthropic 的仅 `conflict_analyst`（8 calls），体量小未必触发自动 caching

### Context utilization 整体表现

- **输出 token 利用率**：0.2%-0.8%（max_tokens=8192 但实际 output 多 < 2K）→ O-C1
- **输入压缩**：Staged processing 有效，但**仅 26/990 calls 触发**（2.6%）→ O-C2
- **单文件 staged processing 中个别文件仍需 18+ full chunks**（如 `tongyi/llm.py`），与上游文件体量大有关

---

## 错误与重试统计

| 错误类别 | 发生次数 | 典型原因 |
|---------|---------|---------|
| `[unknown]` | 133 | OpenAI 代理返回空 content（`finish_reason='stop'` 但 body 为空）、`ThinkingBlock.text` AttributeError |
| `[transport]` | 4 | 代理 Connection error（短暂） |
| `[rate_limit]` | 3 | 429 |
| 总重试/退避事件 | 528+ | 绝大多数在 attempt=2/3 成功恢复 |

Fallback 未被触发；Circuit breaker 未打开；但**信号表明首选 provider 偶发不稳定**。

---

## 通用优化建议（针对项目层面，非测试项目相关）

> 以下建议均从本次运行观测得出，仅针对 `CodeMergeSystem` 通用 agent 设计，不得针对 `dify-official-plugins`。

### O-R1 — Commit Replay：从"全/全无类别规则"升级为"分片 cherry-pick"
**现象**：`src/tools/commit_replayer.py:classify_commits` 要求 commit 内**所有**文件均为 B/D_MISSING 才进入 replay 名单；失败即整 commit 回退到 apply。
**结果**：upstream-51 实测 13/97 可 replay，其中仍有 6 个失败（成功率 54%）。
**建议**：
1. 允许 per-file 子集 cherry-pick：`git cherry-pick -n <sha>` → unstage C-类文件 → 用 `<sha>` 的原始 author/message 提交剩余文件，C 类文件继续走 apply。
2. 保留 per-file `upstream_commit_sha` 元数据到 `FileDecisionRecord`，供 Judge 与 merge_report 追溯。

### O-R2 — Cherry-pick 乐观尝试
**现象**：当前分类仅基于 FileChangeCategory 静态判断，未尝试真实 git 应用。
**建议**：对分类为 B/D_MISSING 的 commit，先做 `git cherry-pick -n` 干跑；若有冲突标记才回退。对分类为包含少量 C 的"准洁净"commit 尝试 `-X theirs` + 复核。

### O-R3 — Cherry-pick 策略升级阶梯
**现象**：`git_tool.cherry_pick()` 失败即 abort，6/13 pure-B-class commits 失败未尝试替代策略。
**建议**：按顺序尝试：
1. 默认 3-way merge
2. `-X theirs`（适合纯 B 类 commit）
3. `--strategy=recursive -X patience`
4. Per-file 分片 replay（O-R1）
5. 降级到 apply 模式

### O-B1 — Anthropic ThinkingBlock 解析
**现象**：`'ThinkingBlock' object has no attribute 'text'` 导致 conflict_analyst 彻底失败，击穿 3 次重试。
**建议**：`src/llm/response_parser.py` 对 Anthropic 响应中的 ContentBlock 按 `block.type` 分发：`text` → `.text`，`thinking` → `.thinking`（或丢弃）。单元测试覆盖 thinking mode enabled 场景。

### O-B2 — UTF-8 Surrogate 预清洗
**现象**：`'utf-8' codec can't encode character '\udc89'` 导致 446+12 files 的 commit-round LLM 全灭。
**建议**：LLM 发送前对任何字符串 payload 走一次 `errors="replace"` 或 `sanitize_surrogates()`；在 `src/llm/client.py` 的请求序列化层加过滤器；并为二进制/unknown-encoding 文件显式走 `take_target`/`take_current` 而非进 LLM。

### O-L1 — human_review 循环回退到 JUDGE_REVIEWING 的死锁
**现象**：首次 judge FAIL + meta_review 后，`src/core/phases/human_review.py` 的 Case 0 判断 `judge_resolution is not None`（≠ `is None`），当 resolution 未设时落到 Case 1 的"not pending"分支，盲目 transition 回 `JUDGE_REVIEWING`，导致无限循环 judge_review（本次测试被此 bug 消耗 ~1h）。
**建议**（**紧急**）：
1. 在 `human_review.py` Case 1 "not pending" 分支增加前置条件：若 `state.judge_verdict is not None and state.current_phase == JUDGE_REVIEW and state.judge_resolution is None`，则直接 `return PhaseOutcome(target_status=AWAITING_HUMAN, checkpoint_tag="judge_resolution_required")`。
2. 或在 Coordinator 的 meta_review 后直接调用 `state_machine.transition(state, AWAITING_HUMAN, "judge failed, needs judge_resolution")` 而不是让 judge_review 返回时走 human_review 的逻辑分支。
3. 增加 state.status=judge_reviewing + dispute_rounds exhausted 时的明确"冷却"标记，防止 orchestrator 自动重入。

### O-D1 — Layer Dependency 阻塞导致 D-missing 漏处理
**现象**：`Layer 3 (models_extensions)` 因 Layer 2 未完成被跳过 → `models/mimo/_assets/icon_s_en.png` 等 9 个 D-missing 文件从未进入 auto_merge，触发 9 个 `d_missing_not_processed` critical issue。
**建议**：
1. Planner 在构建 layered plan 时，将"纯新增文件"（`FileChangeCategory.D_MISSING`，无依赖）集中放到 Layer 0 或独立 "fast track" 层。
2. `_gate_helpers.py` 在 block 时不仅跳过 layer，还要对该 layer 的 D-missing 子集走降级通道（类似 conflict_analyst 的规则解析）。
3. `JudgeAgent` 对 `d_missing_not_processed` 的 veto 判断增加 "still recoverable" 标志，避免最终 verdict 直接 FAIL。

### O-C1 — Max_tokens 过度分配 / Cost 浪费
**现象**：990 次 LLM 调用中 **utilization 0.2%–0.8%**（max_tokens=8192 但 output 多为 1-2K tokens）；按 gpt-5.4 定价，为未用的 output 额度预留了大量预算。
**建议**：
1. 按 agent 调整默认 `max_tokens`：judge=2048，executor=4096（修复任务需要更长），planner=8192（计划需要列 layer/file）。
2. 在 prompt 中明确"请输出 JSON，不超过 N tokens"，并按 JSON schema 压榨结构化输出。

### O-C2 — Staged Processing 覆盖率过低
**现象**：`src/llm/prompt_builders.py:staged_processing` 仅在 26/990 calls 触发（2.6%）；而 input token budget 利用率普遍 < 1%。
**建议**：
1. 将 staged processing 默认开启（当前仅 judge 的大文件触发），对所有 > 10K chars prompt 自动走 relevance 排序。
2. 把 `drop` 决策记录到 `llm_trace` 便于事后审计；drop 过多时降级到 full chunks，避免丢失上下文。
3. 对 OpenAI 模型也引入等价 batching（当前仅 Anthropic 有 `cache_strategy`）。

### O-C3 — Prompt Cache 未命中
**现象**：`cache_read=0, cache_write=0`。config 里 `cache_strategy: system_and_recent` 被设置，但本次 84% 调用走 OpenAI（gpt-5.4），OpenAI provider 忽略此字段；仅 conflict_analyst 的 8 次 Anthropic 调用可能触发 caching，但量太小。
**建议**：
1. 对 OpenAI 自建 prompt caching（通过在 system prompt 开头放一个稳定的"context preamble"，复用跨调用）。
2. `AgentLLMConfig.cache_strategy` 在 OpenAI 模式下若仍设 `system_and_recent`，应打 warning。
3. 在 judge / planner 这类稳定上下文大的 agent 强制将 `system + project_context + merge_plan` 前置为 cache-eligible 区段。

### O-M1 — 记忆跨 dispute round 失效
**现象**：`Memory updated after judge_review: 36 entries total, **0 new, 0 superseded**`。dispute round 内部 LLM 不产生新记忆，也未复用上一轮 repair 记录。
**建议**：
1. dispute round 1/2 开始前，自动把"上一轮的 issues 列表 + executor 修复 diff"注入 judge 的 memory context（作为 `<prior_review>` 块）。
2. Judge 在新一轮看到某 issue 的 `issue_id` 已存在 + 已 repair 时，应视为"已尝试修复"并调整判定权重，而不是重新报告一次相同问题。

### O-M2 — memory_extractor 未被触发
**现象**：by_agent 统计显示 memory_extractor 零调用。
**建议**：核对 `src/agents/memory_extractor_agent.py` 的触发条件（可能仅在"运行结束"阶段触发，而 FAIL 路径未走到）；在 dispute round 结束、meta_review 产生时也应抽取"失败模式"作为持久化记忆。

### O-P1 — Oversize file 硬截断（30 000 chars）
**现象**：`Skipping LLM repair for oversized file models/volcengine_maas/models/llm/llm.py (current=50470 chars, limit=30000)`。直接跳过 → 升级为 human_required。
**建议**：
1. 按 symbol / chunk 粒度做"局部 repair"：仅把出问题的函数送入 LLM 而非整文件。
2. `AgentLLMConfig.executor` 增加 `max_file_chars` 可配置（当前硬编码 30 000）。
3. Oversize 时自动降级为 `take_target` + 标注 `needs_post_merge_review`，避免 judge 报 critical `missing_logic`。

### O-E1 — OpenAI `finish_reason='stop' but empty content` 兜底
**现象**：gpt-5.4 偶发返回 `{"choices":[{"finish_reason":"stop","message":{"content":null}}]}`，分类为 `[unknown]` 后重试。
**建议**：`src/llm/client.py` 对 empty content 的识别归类到 `[provider_empty]`，单独设置更长 backoff（当前 2.3s），避免重试惊群。

### O-F1 — Fallback 触发阈值过高
**现象**：528 次 `[unknown]`/`[transport]` 错误，但 **fallback 零次触发**。原因应为 circuit breaker 阈值为连续失败，绝大多数 call 都在 2-3 次重试内恢复。
**建议**：
1. 增加"滑动窗口错误率"触发条件：过去 N 次调用中失败率 > X% 立即切 fallback，而不仅看连续失败。
2. 对特定错误类别（`ThinkingBlock`、`UTF-8 surrogate`）直接打开 fallback — 这些错误换 provider 通常立即消失。

### O-J1 — Judge per-file 全扫 O(N) 策略成本过高
**现象**：Round 0 即对 ~420 文件逐一做 LLM 调用，re-review 再来一次；本次 judge 总成本占比 66%。
**建议**：
1. 只对 `file_decision_records[fp].confidence < threshold` 或 `decision_source in {LLM, HUMAN_EXECUTED}` 的文件做 LLM judge；高置信度 auto_safe 文件全跳过。
2. 先做 **快速规则判 verdict**（如 `syntax_error` 可用 `ast.parse()` 本地检测）再调 LLM，只对存疑项请求 LLM。

### O-J2 — dispute round 的 veto 漂移
**现象**：Round 0 的 `non_pass` 与 Round 1 re-review 的 428 issues 数量级相当，说明 Executor 的 308 修复未显著降低 Judge 判定，可能因为：
- Executor repair 仅触及 1/3 issue 文件
- Judge re-review 重新"发现"之前未曾标记的 issues
**建议**：
1. Judge 在 re-review 中 freeze 上一轮已标注 issues 列表，**只评估 Executor 的 repair 是否闭合**，不引入新 issue（新 issue 视为 out-of-scope，汇总到 meta-review）。
2. issues 应有全局 `issue_id` 稳定标识，便于 round 间对账。

### O-G1 — `escalate_human` 文件应生成 diff 预览
**现象**：`HumanDecisionRequest.options[*].preview_content` 全为 null；用户决策时只有 `upstream_change_summary` 的一句话。
**建议**：HumanInterfaceAgent 调用前，用 `git_tool.get_file_content` 或 `difflib` 生成上游 vs fork 的 unified diff，填入 preview_content，用户看到真实变更后才能做 semantic_merge 判断。

---

## 诊断：本次循环 bug 的复现最小路径

1. Make any repository produce ≥ 2 dispute rounds in `JUDGE_REVIEW` with `non_pass`.
2. Do NOT provide `judge_resolution` when system pauses (simulate `--no-tui` without external `resume`).
3. Observe: system re-enters `human_review` → re-executes 0 decisions → transitions back to `JUDGE_REVIEWING` → loops indefinitely。

单元测试补丁建议（伪代码）：
```python
def test_human_review_halts_when_judge_verdict_pending_resolution():
    state = MergeState(status=AWAITING_HUMAN,
                       judge_verdict=FAIL_VERDICT,
                       current_phase=MergePhase.JUDGE_REVIEW,
                       judge_resolution=None,
                       human_decision_requests={"f":completed_req})
    outcome = HumanReviewPhase().run(state, ctx)
    assert outcome.target_status == SystemStatus.AWAITING_HUMAN
    assert outcome.checkpoint_tag == "judge_resolution_required"
```

---

## 结论

- ✅ PlannerJudge / Cherry-pick 分类 / CVTE 路由 / Coordinator 批次拆分 / Staged context compression 等核心子系统表现良好，相较 upstream-46 测试有显著进步
- ⚠️ 3 个严重 bug（O-B1 ThinkingBlock、O-B2 UTF-8 surrogate、O-L1 human_review 死循环）必须在下一 release 前修复
- ⚠️ JudgeVerdict 428 issues 中 221 属 `wrong_merge`，暗示 AUTO_MERGE 与 CONFLICT_ANALYSIS 对复杂文件的 semantic 判定仍欠准确
- 整体流程可收敛性取决于 O-L1 修复 + O-J2 收敛策略 + O-M1 跨轮记忆注入
- 建议把 **O-B1 / O-B2 / O-L1** 作为 P0，**O-R1 / O-R3 / O-J1 / O-J2** 作为 P1 纳入下一迭代

**报告作者**：Angel ｜ **生成时间**：2026-04-23
