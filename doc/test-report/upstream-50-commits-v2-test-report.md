# CodeMergeSystem 集成测试报告 — upstream-50-commits-v2

**测试日期**：2026-04-23
**Run ID**：`c25b459f-3758-4990-9022-a30242c12935`
**合并目标**：`dify-official-plugins` 的 `test/upstream-50-commits-v2` → `feat_merge`
**基线**：`feat_merge` 已 reset 至 `d73426c5`（51-commits 测试前纯净态）
**切点 commit**：`19d4300e feat(model): add gpt-5.4-mini and gpt-5.4-nano models (#2754)`（upstream/main~50，与 51-commits 测试无 commit 重叠）
**测试人**：Angel（同时担任人工决策者）
**模型**：planner/conflict_analyst/human_interface/memory_extractor = `claude-opus-4-6` / `claude-haiku-4-5-20251001`（Anthropic）；planner_judge/executor/judge = `gpt-5.4`（OpenAI）
**仓库规则**：`manifest.yaml` 中 `author: cvte` 的插件为二次开发插件；`/models` 下 CVTE 插件存在 dify-api 模型托管；非 CVTE 插件直接采纳上游。

---

## 执行摘要

| 指标 | 值 |
|------|-----|
| 上游提交数（merge-base→HEAD） | **242 commits**（49 本测试范围 + 193 历史桥接）|
| 三向分类文件 | **8436**（A=5848 / B=371 / C=670 / D-missing=430 / D-extra=872 / E=245）|
| 可操作文件 | **1471** |
| Commit Replayer 分类 | 29 fully-replayable / 97 partially-replayable / 116 non-replayable（总 242）|
| Cherry-pick 实际执行（第 1 轮） | **28/31 成功**（1 partial / 2 failed）— 成功率 **90.3%** |
| Plan 自动可合并率 | 54.5%（auto_safe 801 + auto_risky 433 + human_required 6）|
| **最终状态** | ⚠️ **AUTO_MERGE 阶段阻塞在 AWAITING_HUMAN 死循环** |
| JudgeVerdict | **未产生**（阻塞在 AUTO_MERGE，从未进入 JUDGE_REVIEW phase）|
| 总 LLM 调用 | **18**（planner 1 / planner_judge 1 / human_review 4 / judge 6 / executor 2 / auto_merge 2 / initialize 1 / planning 1）|
| 总耗时 | ~58 min（含用户决策等待）|
| 总成本 | **≈ $0.75**（planner_judge $0.25 + 两轮 auto_merge $0.50）|
| Cache 命中 | **cache_read=0, cache_write=0**（gpt-5.4 走 OpenAI，不支持 Anthropic prompt cache；Anthropic 调用量过小未触发）|

---

## Phase 断言记录

### Phase 1 — INITIALIZE
**状态**：✅ COMPLETED（171.5s）
**起止**：07:54:50 → 07:57:26

**关键输出**：
- `Three-way classification: A=5848 B=371 C=670 D-missing=430 D-extra=872 E=245`
- `Commit replay classification: 29 fully-replayable, 97 partially-replayable, 116 non-replayable out of 242`
- `Phase 0.5: 75 upstream interface changes extracted across 26 files`
- `WARNING Phase 0.5: 38 upstream symbols still referenced in fork-only scope`

**断言**：
- [x] 正确识别 `feat_merge` 为 fork、`test/upstream-50-commits-v2` 为上游
- [x] Commit Replayer 的 B/D_MISSING + partial 分类机制生效（P1-批次3 新增的 partial-replayable 分类可见）
- [x] Reverse-impact scanner 完成，38 个 fork-only 引用警告正确产生

---

### Phase 2 — PLAN_REVIEW
**状态**：✅ COMPLETED（Round 0 一次通过）
**起止**：07:56:30 → 07:57:37
**planner_judge**：`gpt-5.4`，1 call / $0.2457（24242 input tokens，utilization 2.57%）

Round 0 verdict：**approved (0 issues)**。摘要："No concrete misclassifications found under the stated review criteria. Security-marked files shown are not classified below auto_risky."

**断言**：
- [x] gpt-5.4 代理兼容性正常（0 次 "model not supported" 错误）
- [x] 0 issues 通过后未无谓触发 plan human review

---

### Phase 2.5 — Plan-level AWAITING_HUMAN（我作为用户的决策）
**状态**：✅ COMPLETED
**起止**：07:57:37 → 08:17:19（约 20 分钟用户离线）

**系统输出 3 个 `human_required` 文件**：

| 文件 | +/- | risk_score | 我的决策 | 理由 |
|---|---|---|---|---|
| `models/tongyi/models/llm/qwen3-coder-480b-a35b-instruct.yaml` | +0/-0 | 0.10 | `downgrade_safe` | 纯格式化（中文标点前后加空格），无 CVTE 端自定义 |
| `models/tongyi/models/llm/qwen3-235b-a22b-instruct-2507.yaml` | +23/-0 | 0.29 | `downgrade_safe` | 格式化 + 参数文档更新，无 CVTE 自定义逻辑 |
| `models/tongyi/models/llm/qwen3-max-preview.yaml` | +23/-1 | 0.29 | `downgrade_safe` | 格式化 + `max_tokens 32768→65536` 上游容量更新 |

**决策 YAML**（`/tmp/merge-upstream-50-v2-decisions-plan.yaml`）：

```yaml
plan_approval: approve
reviewer: angel
item_decisions:
  - file_path: models/tongyi/models/llm/qwen3-coder-480b-a35b-instruct.yaml
    user_choice: downgrade_safe
    notes: "纯格式化（中文标点前后加空格）"
  # ...（共 3 项）
```

**观测问题（O-L2, 下文）**：首次 `merge resume --decisions ...` 成功 apply 3 per-file choices + plan approval，但 resume 进程 **立即退出** 不进入 AUTO_MERGE，报 "Still awaiting human decisions, Pending: 0 files"。需要再次 `merge resume`（不带 decisions）才真正启动下游 phase。

**断言**：
- [x] Plan HUMAN_REQUIRED 文件能正确识别并生成 3 个决策 options（`approve_human` / `downgrade_risky` / `downgrade_safe`）
- [x] YAML 决策加载成功（"Applied 3 per-file choices"）
- [ ] ⚠️ **同一次 resume 未继续到下游 phase**（需再触发一次，见 O-L2）

---

### Phase 3 — Cherry-pick / Commit Replay
**状态**：⚠️ **28/31 成功**（第 1 轮），**0/29 全 fall back**（第 2 轮，剩余冲突 commits）
**起止**：08:17:20 → 08:17:38（第 1 轮）；08:51:25 → 08:51:50（第 2 轮）

**第 1 轮结果**：
- `Replay: 28 commits cherry-picked (1 partial), 2 failed`
- 成功率 **90.3%**（相较 51-commits 的 54%，**显著改善**）
- 说明 P1-批次 3 的「cherry-pick 策略阶梯 + partial replay」修复生效

**第 2 轮结果（剩余冲突 commits）**：
- `Replay: 0 commits cherry-picked (0 partial), 29 failed` — 全部 fall back 到 apply
- 失败原因：这 29 个 commits 涉及 `models/anthropic/`、`models/aihubmix/` 等 fork 有 CVTE 修改或同时有上游改动的文件，3 次策略（3-way → `-X theirs` → `-X patience`）全部无法无冲突合入

**断言**：
- [x] 第 1 轮 P1-批次 3 修复（partial / strategy ladder）显著提升 cherry-pick 成功率（54% → 90%）
- [x] 失败 commit 整洁 fall back，未导致流程崩溃
- [ ] ⚠️ **fall back 后 apply 模式在 `models/anthropic/manifest.yaml` 等文件留下未解决的 UU 冲突**（`<<<<<<< HEAD / ======= / >>>>>>>` 标记未清理），成为下游 AUTO_MERGE 阻塞点

---

### Phase 4 — AUTO_MERGE（两次运行均未达成 consensus）

**第 1 次运行**（08:17:45 → 08:18:52，67s）：
- `Applied user downgrades: 3 files`（tongyi yaml 被降级 auto_safe）
- `ERROR Batch file processing error for tools/vanna/_assets/vanna_configure.png: 'utf-8' codec can't decode byte 0x89`
- Judge 批次审查：3 calls / $0.1991
- 状态：AWAITING_HUMAN（Layer None batch judge sub-review no consensus）

**第 2 次运行**（08:51:53 → 08:53:29，96s）：
- `Replay: 0 commits cherry-picked, 29 failed`（所有未处理 commits 重新尝试）
- 同一 PNG 文件 utf-8 解码错误再次发生
- Judge 批次：3 calls / $0.3042
- 状态：再次 AWAITING_HUMAN

**Judge 判定细节**（解剖第 2 次运行）：

Round 0：
```json
{
  "files": [
    {
      "file_path": "models/anthropic/manifest.yaml",
      "issues": [
        { "issue_level": "critical", "issue_type": "other",
          "description": "Conflict marker '=======' found in merged content" },
        { "issue_level": "critical", "issue_type": "other",
          "description": "Conflict marker '=======' found in merged content" }
      ]
    }
  ]
}
```

Round 1 dispute：Executor 接受修复所有 critical issues（`accepts_all=false, decisions=[{action:"accept"}×N]`），Judge re-review 后部分 withdrawn。

Round 2 re-review：重新对 8 个文件审查，仍报告 info 级 "binary asset content is not inspectable" issues → **not approved** → 超过 `max_dispute_rounds=2` → AWAITING_HUMAN

**断言**：
- [x] 用户 plan-downgrade 正确 apply 到 merge_plan
- [x] Judge 正确识别 `=======` 冲突标记 critical issue
- [ ] ❌ **根本 bug O-M1**：cherry-pick fall back 到 apply 时未清理 UU 冲突标记，Executor 读取原始含 `=======` 的文件内容送给 Judge，判定 critical
- [ ] ❌ **根本 bug O-M2**：Judge 对 "info" 级 issue（PNG 二进制无法检查）视为 non-approved，dispute 永不收敛
- [ ] ❌ **死锁 bug O-L3（O-L1 的 auto_merge 变种）**：Judge no consensus 后 `return AWAITING_HUMAN` 但 `human_decision_requests={}` 无实际 pending 项 → resume 无法推进 → `HumanReviewPhase` Case 2 再次触发 `AUTO_MERGING` → 跑回同一批次 → 循环

---

### Phase 5 / 6 / 7 — CONFLICT_ANALYSIS / HUMAN_REVIEW / JUDGE_REVIEW
**状态**：🚫 **未执行**（阻塞在 Phase 4 AUTO_MERGE）

---

## 最终 JudgeVerdict

**不适用** — 流程未进入 `JUDGE_REVIEWING` 阶段。

AUTO_MERGE 阶段的 batch judge sub-review 充当了部分 judge 角色：对 8 个 risky 文件报告了 2 个 critical (`=======` conflict markers) + 若干 info 级 issues，2 个 dispute rounds 后不收敛。无全局 JudgeVerdict。

---

## 记忆系统输入与利用

| Phase | 条目数变化 | 新增 / 替换 |
|---|---|---|
| initialize | 0 → 21 | +21 / 0 |
| planning | 21 → 24 | +3 / 0 |
| plan_review | 24 → 24 | +0 / 0 |
| human_review | 24 → 20（第一次）/ 24（第二次） | +0 / -4 superseded（第一次）|
| auto_merge（第 1 次） | 20 → 50 | +30 / -4 superseded |
| auto_merge（第 2 次） | 50 → 50 | +30 / 0（冗余，与第一次内容一致）|

**观测问题**：
- `memory_extractor` agent 本次未被触发（by_agent 统计 0 次 memory_extractor 调用），与 51-commits 测试结论一致（见 O-M4）
- 两次 AUTO_MERGE 运行期间 Memory 输出相同 30 条，说明记忆未跨 dispute/resume 生效 —— 同样的 critical issue 反复触发，dispute round 未复用上一轮修复事实（O-J2 继承 51-commits 老问题）

---

## Agent LLM 上下文压缩情况

### 本轮 Staged Processing
- **总 LLM 调用**：18 次
- **Staged processing 触发**：0 次（本测试 prompt 普遍 < 20K chars，未达到压缩阈值）
- **相关现象**：AUTO_MERGE 阶段 Judge 的 prompt 仅 15,582 chars / 4,452 est_tokens，远未用到 context budget 上限 823,691

### Prompt Cache
| 指标 | 值 |
|------|-----|
| `cache_read` | **0** |
| `cache_write` | **0** |

原因：
- 83% 调用走 OpenAI (gpt-5.4)，OpenAI provider 忽略 `cache_strategy: system_and_recent`
- 警告明确打印：`cache_strategy='system_and_recent' has no effect on OpenAI (gpt-5.4); Anthropic-only. Set cache_strategy='none' to silence this warning.`
- Anthropic 调用体量（planner）本次仅 0 次实际调用（因 planner 模型已改为 `claude-opus-4-6` 但 planning phase 输出被 planner agent 内部截断/快速返回）

### Context Utilization
- **平均 utilization**：0.52%（18 calls 平均）
- **峰值**：planner_judge 2.57%（24242 input tokens / 8192 max_tokens）
- **最低**：auto_merge judge round 0 0.23%（6,525 est_tokens / 823,690 budget）
- **评估**：`max_tokens=8192` 过度配置（51-commits 结论相同，O-C1 未改）

### Error / Retry
| 错误类别 | 次数 | 原因 |
|---|---|---|
| PNG utf-8 decode error | **2** | `tools/vanna/_assets/vanna_configure.png` 二进制文件被当文本送入 AUTO_MERGE 批处理 |
| Judge no consensus | **2** | 同一批次 dispute 超 2 轮 |
| LLM 实际失败 | 0 | 所有 LLM calls `success: True, attempt=1/3` |

---

## 通用优化建议清单

> 以下建议均从本次运行观测得出，针对 `CodeMergeSystem` 通用 agent 设计（非测试项目相关）。

### O-M1（🔴 P0）— apply fall-back 必须清理 UU 冲突标记
**现象**：cherry-pick 全策略失败后 fall back 到 apply 模式，但 apply 模式直接把 `<<<<<<< / ======= / >>>>>>>` 留在文件中未解决。Executor 读入这些标记送给 Judge，被判定为 critical `wrong_merge`。
**建议**：
1. `src/tools/commit_replayer.py` fall-back 到 apply 前，对每个 apply 前/后的文件检测 `<<<<<<<`/`=======`/`>>>>>>>` 标记，若检出则强制路由到 conflict_analysis / human_required，而不让 AUTO_MERGE 处理。
2. `src/agents/executor_agent.py` 写入前对 `apply_with_snapshot` 的输入做同样检测，若含冲突标记直接 raise `ConflictMarkerLeftover` 异常，由上层降级处理。
3. 给 `FileDecisionRecord` 加 `has_unresolved_conflict_markers: bool` 标志位，Judge 遇到时固定判 `needs_human` 而不是 critical。

### O-M2（🔴 P0）— Judge 对 info 级 issue 不应阻止 approved verdict
**现象**：Judge Round 2 对 PNG/二进制文件报 `info` 级 "binary asset content is not inspectable" → `approved=false` → dispute 超限。
**建议**：
1. `src/agents/judge_agent.py` 的 verdict 判定：`approved = all(issue.level != 'critical' and issue.level != 'high')`（忽略 info/low）。
2. info/low 级 issue 仅记入 `verdict.advisories[]`，不参与 consensus 判断。
3. `VerdictSchema` 增加 `blocking_levels: list[str]` 字段（默认 `['critical','high']`），让阈值可配置。

### O-L3（🔴 P0）— AUTO_MERGE no-consensus 死循环（O-L1 变种）
**现象**：`auto_merge.py:441` 在 batch judge sub-review 不 consensus 时直接 `return AWAITING_HUMAN`，但 **不创建任何 `HumanDecisionRequest`**。HumanReviewPhase Case 2 看到 `plan_human_review.decision=APPROVE` → transition 回 `AUTO_MERGING` → 同批次再跑 → 再不 consensus → 循环。本次 resume 3 次均卡同一批次。
**建议**：
1. `auto_merge.py` no-consensus 时，为涉及的 N 个文件创建 `HumanDecisionRequest`（状态=pending，含 unified diff preview + judge issues 摘要），让 `HumanReviewPhase` 的 Case 1 能正常走人工决策分支。
2. 或增加 `state.auto_merge_dispute_exhausted_batches: set[str]`，下次 `HumanReviewPhase` 检测到后直接 transition 到 `FAILED` 而不是 `AUTO_MERGING`。
3. 参照 O-L1 修复模式，在 `human_review.py` 增加 Case 0.5：`if current_phase==AUTO_MERGE and status==AWAITING_HUMAN and not human_decision_requests: return AWAITING_HUMAN stay`。

### O-L2（🟡 P1）— Plan decisions 首次 resume 无法推进下游 phase
**现象**：`merge resume --run-id X --decisions plan.yaml` 成功 "Applied 3 per-file choices" + "Plan approval set to 'approve'"，但同一 resume 进程立即报 "Still awaiting human decisions, Pending: 0 files" 退出。需要第二次 `merge resume` 才真正启动 AUTO_MERGE。
**建议**：
1. `src/cli/commands/resume.py:56-167` 的 plan_approval 分支写入后，显式 `ctx.state_machine.transition(state, SystemStatus.AUTO_MERGING, "plan approved via CLI decisions file")` 再进入 `orchestrator.run()`；当前逻辑依赖 `orchestrator.run() → HumanReviewPhase → Case 2` 跳转，在部分 edge case 下会误判为"仍在 awaiting"。
2. 或在 plan-level decisions 加载后直接调用 `await HumanReviewPhase().execute(state, ctx)` 一次，确保状态机前进。

### O-B3（🟡 P1）— 二进制文件（PNG/ico/woff/assets）进入文本批处理
**现象**：`tools/vanna/_assets/vanna_configure.png` 被放入 AUTO_MERGE 的 batch file processing 循环，按 UTF-8 解码 → 报 `'utf-8' codec can't decode byte 0x89 in position 0`（PNG 魔数）。
**建议**：
1. `src/core/phases/auto_merge.py` 批处理前白名单过滤：基于文件扩展名（`.png/.jpg/.jpeg/.gif/.ico/.svg/.woff/.ttf/.eot/.mp3/.mp4/.zip/...`）自动分类为 `binary_asset`，走二进制 diff（sha256 对比）而非文本流。
2. `src/models/plan.py` `FileChangeCategory` 增加 `BINARY_ASSET` 类别。
3. 对 `BINARY_ASSET` 类默认 `take_target`（非 CVTE）或 `escalate_human`（CVTE）；不送入 LLM。

### O-M3（🟡 P1）— Memory 跨 resume 重复注入
**现象**：第 1 次 auto_merge 记忆 +30 new / -4 superseded = 50 total；第 2 次 auto_merge 同样 +30 new / -0 superseded = 50 total。第 2 次 re-extract 应识别出已存在记忆而 skip，实际未做。
**建议**：`src/agents/memory_extractor_agent.py` 在写入前按 `(phase_id, semantic_fingerprint)` 去重；或 orchestrator 在 resume 时 skip 已覆盖 phase 的 memory extraction。

### O-M4（🟡 P1）— memory_extractor agent 未被触发（51-commits 同现）
**现象**：本次 18 个 LLM calls 中 `memory_extractor` 调用数 **0**，与上次 51-commits 结论一致。
**建议**：检查 `src/agents/memory_extractor_agent.py` 触发条件（可能仅在"运行最终完成"阶段触发）；应在 phase 完成边界（尤其 auto_merge / judge_review 结束）也触发一次抽取。

### O-R4（🟢 P2）— cherry-pick 策略阶梯改进显著，保留并文档化
**现象**：第 1 轮 28/31 成功（90.3%），相比 51-commits 测试的 7/13（54%）有巨大改进。P1-批次 3 的 partial cherry-pick + strategy ladder 修复生效。
**建议**：
1. 在 `commit_replayer.py` 添加每次 fall back 的 **metrics 记录**（strategy tried, fallback reason），写入 `merge_report.json`。
2. 对 partial 成功率 < 50% 的 commit 自动生成 "需人工 rebase" 标注。
3. 考虑对 pure-B fall back 失败的 commits 尝试第 4 策略：`git cherry-pick --strategy=recursive -X theirs -X patience --keep-redundant-commits`。

### O-C1（继承 51-commits）— max_tokens 过度分配 / utilization 0.52%
**现象**：18 calls 平均 utilization 0.52%（上次 0.2%-0.8%），`max_tokens=8192` 普遍 over-provision。
**建议**（未改，重申）：按 agent 调整 `max_tokens`：judge=2048 / executor=4096 / planner=8192。

### O-C3（继承 51-commits）— OpenAI 分支 prompt cache 全未命中
**现象**：9/18 calls 走 gpt-5.4，cache_read=0 / cache_write=0。
**建议**（未改，重申）：为 OpenAI 自建 prompt caching（在 system prompt 前置稳定 context preamble 复用跨调用）；OpenAI 模式下 `cache_strategy=system_and_recent` 时打 warning（本次已打）。

---

## 对比 51-commits 测试

| 维度 | 51-commits | 50-commits-v2 | 改善 |
|---|---|---|---|
| Cherry-pick 成功率 | 7/13 (54%) | 28/31 (90%) | ✅ +36pp |
| AUTO_MERGE 是否完成 | 是（$7.45, 31.8min） | ❌ 死循环阻塞 | 🔴 退化 |
| Judge 循环 bug | 发生（O-L1）| 换位置发生（O-L3）| 🟡 未根治 |
| PlannerJudge 代理兼容 | 失败 → 全升级 HUMAN | 正常 | ✅ 稳定 |
| Plan decisions resume | 正常 | 首次退出 bug（O-L2）| 🟡 新退化 |
| UTF-8 surrogate（O-B2）| 发生 446+12 files | 仅 1 PNG 文件（新路径 O-B3）| ✅ 部分修复 |
| ThinkingBlock（O-B1）| 发生 | 未复现（anthropic 调用少）| ✅ 或未验证 |

**结论**：P1-批次 3 的 cherry-pick 策略阶梯修复效果显著（O-R3）；O-B1 / O-B2 大部分缓解；**但 AUTO_MERGE 阶段因 UU 冲突标记 + Judge info-level 漂移触发新死循环，阻塞比 51-commits 更早**。

---

## 诊断：本次死循环最小复现路径

1. 配置 max_dispute_rounds=2（默认）
2. 构造一个包含 `models/anthropic/manifest.yaml` 这类 fork 有 CVTE 修改的批次
3. 让 cherry-pick 所有策略失败 → fall back 到 apply
4. apply 留下 `<<<<<<< HEAD / ======= / >>>>>>>` 标记
5. Executor 读入文件内容送 Judge
6. Judge Round 0 报 critical `wrong_merge`（Conflict marker found）
7. Executor Round 1 `accepts_all=false` 声明已修复
8. Judge Round 1 审视 8 文件（同批次）再报 info（binary asset not inspectable）+ 部分未修复 critical
9. 超 max_dispute_rounds=2 → AWAITING_HUMAN（无 pending request）
10. orchestrator.run → HumanReviewPhase Case 2 → AUTO_MERGING 无限循环

**单元测试建议**（伪代码）：

```python
async def test_auto_merge_no_consensus_creates_human_decision_requests():
    # Setup: batch with unresolved conflict markers
    state = make_state_with_files([
        ("models/anthropic/manifest.yaml", "<<<<<<< HEAD\na\n=======\nb\n>>>>>>>")
    ])
    ctx = make_ctx(max_dispute_rounds=1)

    outcome = await AutoMergePhase().execute(state, ctx)

    assert outcome.target_status == SystemStatus.AWAITING_HUMAN
    # Should create actual pending requests, not empty
    assert len(state.human_decision_requests) > 0
    pending = [r for r in state.human_decision_requests.values() if r.human_decision is None]
    assert len(pending) > 0
```

---

## 结论

- ✅ **P1-批次 3 cherry-pick 策略阶梯修复效果显著**（54% → 90%）
- ✅ P0-批次 1（PlannerJudge 代理兼容）稳定
- ✅ Plan-level human review 决策加载流程基本可用
- 🔴 **新 P0 bug（O-M1/O-M2/O-L3）导致 AUTO_MERGE 阶段死循环**，测试未能跑通到 JUDGE_REVIEW
- 🟡 O-B2（UTF-8 surrogate）在新二进制场景 O-B3 再次暴露
- 🟡 Memory 跨 resume 重复注入、memory_extractor 零触发（O-M3/O-M4）
- 优先级：**O-M1 / O-M2 / O-L3 必须在下个 release 前修复，否则系统在有 fork CVTE 修改 + 二进制资源 + cherry-pick 失败的真实场景下不可用**

**报告作者**：Angel ｜ **生成时间**：2026-04-23
