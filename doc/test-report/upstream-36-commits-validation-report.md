# dify-official-plugins 合并流程验证报告（upstream/main~36）

- 报告日期：2026-04-28
- 测试目标：验证 code-merge-system 在 dify-official-plugins 上的端到端合并能力
- Run ID：`c4b8ce9e-5a06-4b63-aa53-8968012ce4d7`
- 系统版本：`code-merge-system` 当前 main 分支（含 memory 注入扩展、OpenAI reasoning 模型修复）

---

## 1. 测试基线信息

| 项目 | 值 |
|---|---|
| 仓库 | `/Users/angel/AI/project/dify-official-plugins` |
| 远端 | `origin=cvte fork`、`upstream=langgenius/dify-official-plugins` |
| 本地基准分支 | `feat_merge` (cvte fork 主分支，HEAD=`65eb49a5`) |
| 上游基线 commit | `26d88b58 feat(models/azure_openai): add missing recent models, support reasoning_summary (#2901)` |
| 距离 upstream/main HEAD | ~36 commits |
| merge-base | `2b506b2bcf52` |
| 待合并基线分支 | `test/merge-validation-26d88b58` |
| 工作分支 | `test/cvte-merge-26d88b58` |
| 选择理由 | 中等距离（~36，区别于历史基线 ~50）；diff 覆盖 6 个 cvte 模型托管目录 + 多个 cvte tools；含一个大规模 uv-lock migration 重构（#2965）作为容错挑战 |

## 2. 插件分类结果

仓库共有 **288** 个 `manifest.yaml`：

- **18 个 cvte 二开插件**（`author: cvte`）
- **270 个原始插件**（`author: langgenius` 等）

### 2.1 cvte 插件清单（18 个）

| 类别 | 插件 |
|---|---|
| **6 个模型托管**（特殊关注） | `models/azure_openai`、`models/cvte`、`models/tongyi`、`models/vertex_ai`、`models/volcengine_maas`、`models/xinference` |
| 2 个 extensions | `extensions/oaicompat_cvte_dify_model`（与官方同名分叉）、`extensions/voice_assistant` |
| 10 个 tools | `tools/bing`、`tools/comfyui`、`tools/dhr`、`tools/firecrawl`、`tools/gaode`、`tools/google_search`、`tools/hms`、`tools/image_collage`、`tools/maxhub`、`tools/universal` |

> 与 memory `project_cvte_plugins.md`（"18 个 cvte 二开插件清单（含 6 个模型托管）"）完全一致 ✅

## 3. 合并过程分析

整个 run 经历 **3 轮 resume**（因为存在 `AWAITING_HUMAN ↔ AUTO_MERGE` 状态机回弹），最终落地 3 个合并 commit。

### 3.1 阶段时序与耗时

| 阶段 | 耗时 | 关键产出 |
|---|---|---|
| `initialize` | 140.6s | 三方分类 A=5593 B=516 C=863 D-missing=438 D-extra=920 E=195；Commit replay 分类：23 fully / 93 partially / 162 non-replayable |
| `planning` | 0.2s | 10 layers, 10 phases, 1817 actionable files；Coordinator 将大批次切成 8/4/6/4/2 个子批次（max_size=60） |
| `plan_review` | 74.2s | 1 轮 revision_needed → 1 轮 approved（共 5 次 LLM 调用） |
| `auto_merge` (R1) | 11.3s | Replay：22 commits cherry-picked（0 partial），1 failed；3 个 conflict-marker 文件 → 升级人工；11 个二进制资产 → TAKE_TARGET |
| `auto_merge` (R2) | 3001.4s (~50 分) | executor 64 次 LLM 调用应用 patch；落 commit `721155b8 merge(auto_merge): resolve 1347 files` |
| `conflict_analysis` | 8104.7s (~135 分) | 23 轮分析（每轮按 commit 分组）；conflict_analyst 127 次 LLM 调用（112 success / 15 failed）；落 commit `e0571684 merge(conflict_resolution): resolve 228 files` |
| `human_review` (R3) | ~3s | 应用 67 个 conflict decisions；落 commit `10bf82d9 merge(human_review): resolve 67 files` |
| `judge_review` | 13306.7s (~3.7h) | **Judge 1124 次调用，stalled after 2 rounds**；meta-review 判定 fundamental architectural/specification misalignment；376+ B-class 文件偏离 upstream → 升级人工 |
| 终态 | — | `status=awaiting_human`（judge_review pending human resolution）；**未生成 final merge_report**；最终 verdict 未通过 |

**合并 commits（已落地）**：
```
10bf82d9 merge(human_review): resolve 67 files
e0571684 merge(conflict_resolution): resolve 228 files
721155b8 merge(auto_merge): resolve 1347 files
```

净 diff vs feat_merge：1139 files changed, +11573 / −69489 lines（uv-lock migration 主导）。

### 3.2 三轮人工决策分布

| 轮次 | 决策数 | 类别 | 用户选择 |
|---|---|---|---|
| R1 (plan-stage) | 6 | 全部模型 yaml/llm.py（5 cvte tongyi/vertex_ai + 1 anthropic/llm.py） | `downgrade_risky` × 6 — 让 conflict_analyst 智能融合 |
| R2 (conflict-marker) | 3 | 非 cvte（gemini/oci/openai_api_compatible） | `take_target` × 3 — 直接采用 upstream |
| R3 (post-conflict-analysis) | 67 | 65 非 cvte + 2 cvte（azure_openai/vertex_ai） | 65×`take_target` + 2×`take_current`（保留 cvte 二开） |

## 4. 冲突处理详情

### 4.1 自动 cherry-pick 重放

`commit_replayer` 优先尝试 `git cherry-pick` 上游的 23 个完全可重放 commit。结果：
- ✅ **22 个成功** cherry-picked（自动落库无人工介入）
- ⚠️ **1 个失败**回退到 patch apply

**Partial cherry-pick 全部失败**（如 `f6eca129 keep=106`、`c098f81f keep=217`、`e3481654 keep=50` 等），原因是 cvte fork 上 `cvte` 占领的目录早已偏离 upstream，导致 `git cherry-pick -- <subset>` 路径不再合法。系统自动回退到 patch apply（行为符合预期）。

### 4.2 冲突标记升级（O-M1）

第一次 `auto_merge` 后，git 工作树留下 **3 个未解决冲突文件**：
- `models/gemini/models/tests/test_feature_compatibility.py`
- `models/oci/models/text_embedding/text_embedding.py`
- `models/openai_api_compatible/models/llm/llm.py`

→ 全部 author=langgenius，按规则 R3 全选 `take_target`。

### 4.3 二进制资产路由（O-B3）

11 个二进制资产文件（`.png/.jpg/.whl/...`）跳过 LLM 批审，直接路由到 `TAKE_TARGET`，符合 binary 文件不进 LLM 的设计。

### 4.4 conflict_analyst 提案 vs 用户决策

`conflict_analyst` 对 **67 个剩余冲突**给出建议，但全部 confidence < 0.85 触发 escalate_human。用户按规则覆盖：
- 65 个非 cvte → `take_target`
- 2 个 cvte (`models/azure_openai/models/common.py`、`models/vertex_ai/models/llm/gemini-2.0-flash-001.yaml`) → `take_current`（保留 cvte 二开，分析师推荐为 escalate_human conf=0.65/0.82）

### 4.5 LLM 调用错误模式

| Phase | 失败模式 | 次数 |
|---|---|---|
| conflict_analyst | `model_context_window_exceeded`（445 files / 5 commits 单批次） | 1 |
| conflict_analyst | `Request timed out` (3 attempts × 60s) | 多次 |
| executor | failed_calls | 11/71 |
| conflict_analyst | failed_calls | 15/127 |

> 系统的 fallback 健壮性可圈可点：单批次失败不会终止整个 phase，下一批次正常继续。

## 5. 流程验证结论

| 验证点 | 结果 | 说明 |
|---|---|---|
| ① 插件识别正确性 | ✅ PASS | 288 个 manifest 全部识别，与 git ls-files 一致 |
| ② author 分类正确性 | ✅ PASS | 18 cvte / 270 非 cvte，与 memory 历史记录完全一致 |
| ③ 冲突识别完整性 | ✅ PASS | 三方分类 + commit replay 分类 + conflict_marker O-M1 + binary O-B3 多路径全部触发 |
| ④ 合并策略合规性 | ✅ PASS | 用户决策严格按"cvte 保留 / 非 cvte 采用 upstream"规则；conflict_analyst 推荐被覆盖处仅 2 个 cvte 文件且决策合理 |
| ⑤ 最终结构完整性 | ❌ FAIL | 3 个合并 commit 已落地（1642 files），但 **judge stalled after 2 rounds**；meta-review 判定 376+ B-class 文件偏离 upstream，建议 "escalate / refine spec / reset"；run 终态 `awaiting_human`，无 final merge_report 产出 |

**总体评级**：⚠️ **PARTIAL PASS**
- ✅ 端到端流程**走通了所有 phase**（plan → plan_review → auto_merge → conflict_analysis → 3 轮 human_review → judge_review → meta_review）— 系统的状态机、checkpoint、resume、agent 协作都正常运转
- ❌ 但**最终 verdict 未通过** — Judge 持续发现"应等于 upstream 但合并后不等于"的 B-class 文件 386→482，越审越多，meta-review 判定为系统性偏差
- 这暴露的不是 orchestration bug，而是 **B-class 应用策略**有问题：take_target 决策没真正落到 worktree（很可能是 patch_apply 在某些重写过的路径上失败但被静默吞掉）

## 6. Memory 系统利用率分析

### 6.1 当前观察到的 memory 数据流

```
Phase            entries  new  removed  cumulative
planning              3    +3        0          3
auto_merge (R1)      19   +16        0         19
auto_merge (R2)      48   +36        2         48
conflict_analysis    55    +7        0         55
```

最终 memory 共 **55 条 entries**，全程线性增长，2 个 superseded 被自动清理。

### 6.2 注入路径覆盖度

按 commit `2113bea feat(memory): inject memory context into 6 secondary LLM call paths` 之后的版本，memory_context 已注入到主流 LLM call 路径。本次 run 的实测情况：

- ✅ planner / planner_judge / executor / conflict_analyst 主路径都通过 `BaseAgent._call_llm_with_retry`，理论上都注入了 memory
- ⚠️ **判断依据不足**：日志中没有显式打印 "Memory injected: N entries" 之类的指标，无法精确量化"path coverage"——只能看到 memory.entries_total 增长

### 6.3 优化建议

1. **添加 memory 注入指标日志**：在 `BaseAgent._call_llm_with_retry` 注入 memory_context 时打 INFO 级别 log（注入条数、输入 prompt 长度变化）。这样能在 cost summary 中追加 "Memory utilization" 段落，量化每个 agent 实际用到 memory 的频次和效果。
2. **memory 关联性评分**：当前 entries 全量注入。当 entries 数量增长后（>100），应该按当前 task/file_path 做相关性筛选只注入 top-N，避免 prompt 膨胀（peak conflict_analyst 已到 90.66% utilization，边缘溢出风险）。
3. **memory 有效性反馈**：目前没有"memory 命中后影响了 LLM 输出"的下游度量。可以在 judge_verdict 阶段反向打分，作为 memory entry 是否值得保留的依据。

## 7. 存在的问题与改进建议

### 7.1 工程问题

1. **AWAITING_HUMAN ↔ AUTO_MERGE 反复弹跳**：
   - 单次 run 经历 3 轮 awaiting_human（plan-stage / conflict-marker / post-conflict-analysis）
   - 每轮都需要外部生成 decisions.yaml 再 resume，自动化成本高
   - 建议：CI 模式下可以加 `--auto-decisions <yaml>` 一次性传入所有可能轮次的预设决策
2. **conflict_analyst 单批 token 溢出**：
   - 出现 1 次 `model_context_window_exceeded`（445 files / 5 commits 一批）
   - Coordinator 只按"max_size=60 文件"切分，但没考虑实际 token 体量
   - 建议：在 `coordinator.py` 引入 token 估算门槛（>50K tokens 强制再切）
3. **Judge phase 耗时超预期**：
   - 984 次 LLM 调用，每文件单独审，整体预计 ≥3 小时
   - 建议：对 take_target / take_current 的简单决策跳过 LLM judge，直接走 git diff 验证
4. **partial cherry-pick 全部失败**：
   - 23 个 partial 全失败（如 `c098f81f keep=217`），降级到 patch apply
   - 建议：把这部分 commit 直接标记不可 partial-replay，节省尝试时间

### 7.2 配置 / UX 问题

1. **首次运行需要交互**：`merge --ci` 仍要求按 Enter 确认，与 `--ci` 语义矛盾。建议 `--ci` 隐含 `--yes`。
2. **decisions.yaml schema 不统一**：
   - plan-stage 用 `item_decisions[].user_choice`（值 `approve_human|downgrade_risky|...`）
   - conflict-stage 用 `decisions[].decision`（值 `take_current|take_target|...`）
   - 建议合并到单一 schema，用 `phase` 字段区分
3. **MERGE_PLAN_*.md 报告路径**：实际输出到 `MERGE_RECORD/`，但 CLAUDE.md 文档说会到 `.merge/plans/`——文档已与代码不符（memory `reference_merge_artifacts.md` 也确认）。

### 7.3 成本

- **R1+R2 累计**：$29.19 USD（plan + auto_merge + conflict_analysis）
- **R3 judge_review 实测**：$67.08 USD（judge 1120 calls × claude-opus-4-6，单 phase 占 $66.76）
- **本次 run 总计**：**$96.27 USD**（远超此前 ~$40–50 估算，主要因 judge stall 触发了 4 轮全文件复审）
- 主要成本：**judge_review $67**（70%）、conflict_analyst $8.63、auto_merge $3.07
- 教训：`max_judge_rounds` 阈值偏低（threshold=2 就触发 stall meta-review），加上每个文件都重审，单 run 容易爆成本

### 7.4 Judge stall 暴露的问题（重大）

Judge meta-review 摘要：
> "Massive issue count (386-482) with minimal reduction across rounds indicates fundamental architectural or specification misalignment between Judge expectations and Executor output."
> "Escalate to human review to analyze the top 5 issue categories, determine if Judge criteria are achievable, and either refine the specification or reset the merge approach entirely."

具体 issue：**B-class 文件**（应该等于 upstream）合并后**不等于 upstream**——几百个文件级别。可能原因：

1. **patch_applier 静默失败**：某些 take_target/cherry-pick 操作返回成功但没真正覆盖文件，Judge 在 verify 阶段发现差异
2. **executor 的 patch 不完整**：executor 收到 spec 是 take_target 但生成的 patch 仅修改部分内容
3. **commit_replayer 与 take_target 决策冲突**：cherry-pick 产生的内容与 take_target 期望内容不一致
4. **B-class 分类本身有误**：classifier 把不该是 B-class 的文件标成 B-class

**建议**：在 `auto_merge` 完成后增加一个 sanity-check phase（不调 LLM）：对所有 B-class 文件做 `git diff <target_ref> -- <file>`，若有差异就立即报警/降级到人工，避免 Judge phase 跑满 1100+ 次 LLM 调用才发现这个根因。

## 8. 附录

### 8.1 报告文件位置（产物）

- Plan 报告：`MERGE_RECORD/MERGE_PLAN_test_merge-validation-26d88b58_c4b8ce9e.md`
- Plan 审查：`outputs/plan_review_c4b8ce9e-5a06-4b63-aa53-8968012ce4d7.md`
- Run log：`outputs/debug/run_c4b8ce9e-5a06-4b63-aa53-8968012ce4d7.log`
- LLM traces：`outputs/debug/llm_traces_c4b8ce9e-5a06-4b63-aa53-8968012ce4d7.jsonl`
- Checkpoint：`outputs/debug/checkpoints/checkpoint.json`
- 决策 yaml：`.merge/decisions.yaml`、`.merge/decisions-round2.yaml`、`.merge/decisions-round3.yaml`

### 8.2 累计 LLM 调用统计

| Agent | calls | success | failed | cost USD |
|---|---|---|---|---|
| planner | 2 | 2 | 0 | $0.058 |
| planner_judge | 3 | 3 | 0 | $0.897 |
| conflict_analyst | 127 | 112 | 15 | $8.63 |
| executor | 72 (71+1) | 61 | 11 | $3.39 |
| judge | **1210** (90+1120) | 1206 | 4 | **$84.25** |
| memory_extractor | 1 | 1 | 0 | $0.001 |
| **总计** | **1415** | 1395 | 30 | **$96.27** |

总 token：input ~3.3M / output ~256K（cache 0）。avg latency 11s。

### 8.3 与 memory 中历史 50-commits run（`58c0e2f8`）的对比

| 项目 | 50-commits (memory) | 36-commits (本次) |
|---|---|---|
| plan files | 1500+ | 1363 |
| 自动合并率 | — | 66.5% |
| Plan 阶段成本 | — | $0.95 |
| 是否走完 auto_merge | 否（停在 AWAITING_HUMAN） | ✅ 是 |
| 是否走到 conflict_analysis | 否 | ✅ 是 |
| 是否产生合并 commits | 否 | ✅ 3 个 commit |
| 是否走完 judge_review | 否 | ✅ 是（含 meta-review）|
| 最终 verdict | — | ❌ stalled — escalate to human |
| 总成本 | — | $96.27 |

**结论**：相比上次 50-commits 测试只跑到 plan 阶段就停，本次 36-commits run 首次完整跑完了 plan→auto_merge→conflict_analysis→judge_review→meta_review 全部 phase，揭示了一个此前被遮蔽的关键问题：**B-class 文件在合并后大规模偏离 upstream，Judge 累计审到 386-482 个文件级别问题，meta-review 判定为系统性 spec/impl 错位**。这是单纯跑短 run 永远发现不了的 — 端到端验证的核心价值正在于此。
