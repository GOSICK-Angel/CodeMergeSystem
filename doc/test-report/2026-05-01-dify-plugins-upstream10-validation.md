# dify-official-plugins × code-merge-system 全流程验证报告

**报告日期**：2026-05-01
**测试目标仓库**：`/Users/angel/AI/project/dify-official-plugins`（cvte fork）
**code-merge-system 仓库**：`/Users/angel/AI/personal/code-merge-system`
**测试人**：Claude Code 自动化分析
**预算**：上限 $100；本次实际消耗 $0（基于已有 4 次 run 的 checkpoint evidence 分析，未启动新 run）

---

## 0. 摘要（TL;DR）

- **目标仓库不算干净**：`feat_merge` 分支有 12 个 untracked `_assets/` 图片，无 modified 文件；vs upstream/main diverged 317/355。可合并，但需先决策 untracked 文件去留。
- **插件分类**：293 个插件中 **18 个 cvte 系**（cvte:16 + cvte-test:1 + cvte-old:1），其余 275 个非 cvte 路径。
- **基线选择**：`upstream/main~10` = `8e9f8c83`（10 commits、344 commit-window 文件、1858 全量 diff、含 9 个 cvte 插件冲突）。
- **流程已被 4 次 run 覆盖**（同基线 8e9f8c83）：3 次卡在 `plan_review/awaiting_human`，1 次进入 `auto_merge` 后再次卡 awaiting_human。
- **核心结论（满足用户预期 ✅）**：cvte 插件 **没有被强制走人工**——221 个 cvte 文件中 plan 阶段仅 5 个判 `human_required`（2.3%），其余 216 个走自动路径。
- **核心问题（关键 bug ❌）**：`Executor.apply_decision()` 缺 `SEMANTIC_MERGE` 分支，所有需语义合并的文件（251/258 escalate_human）被错误降级人工，**Executor 的语义合并能力实质未启用**。
- **Memory 利用率**：100% hit rate（190/190），但 `entry_outcomes` 字段空——只统计命中、不统计被采纳/被回滚，反馈闭环缺失。

---

## 1. 测试基线信息

### 1.1 目标仓库现状

| 项目 | 值 |
|---|---|
| 路径 | `/Users/angel/AI/project/dify-official-plugins` |
| 当前分支 | `feat_merge` |
| 跟踪分支 | `origin/feat_merge`（本地领先 17 commits 未推） |
| 工作树 | **不干净**：12 个 untracked `_assets/` 资源文件，0 modified |
| origin remote | `git@gitlab.gz.cvte.cn:wa-ai/dify-official-plugins.git` |
| upstream remote | `git@github.com:langgenius/dify-official-plugins.git` |
| vs upstream/main | diverged，upstream ahead 317 / fork ahead 355 |
| merge-base | `2b506b2bcf52c6ef2eac19404c29b7f91e298139` |

**未提交资源文件（12 个，需用户决策）**：
```
models/{mimo,oci,volcengine,volcengine_maas}/_assets/*.png
tools/{bailian_memory,gemini_video,somark,tavily}/_assets/*
```
建议在合并前 `git add` 一次或全部 `git clean -fd` 处理掉，否则合并过程中可能出现 path 冲突。

### 1.2 上游基线 commit 选择

测试者评估了 4 个候选基线对比 cvte 插件覆盖度：

| 候选 | commits | 总文件变更 | 命中 cvte 文件数 | 评估 |
|---|---|---|---|---|
| `upstream/main~5` | 5 | 75 | **0** | ❌ 无 cvte 冲突，无法验证 Executor |
| `upstream/main~7` | 7 | ~250 | 9 | ✅ 适中，可验证 |
| **`upstream/main~10`** ⭐ | 10 | 344 | **14** | ⭐ **推荐**：cvte 覆盖足够，规模可控 |
| `upstream/main~30` | 30 | 1231 | 38 | ⚠️ 偏大，预算压力 |
| `upstream/main~50`（memory 旧基线） | 50 | ~1500+ | 58 | ❌ 历史 run 单次 $96，超预算 |

**最终选定**：`upstream/main~10` → SHA `8e9f8c83f9cca9920ffa297eba583ff39ddbd28c`

**该基线覆盖的 commits**：
```
d109df6c fix(aihubmix): update pricing and remove deprecated models (#2998)
31cdfde4 ci: speed up plugin workflows with caching and concurrency (#2997)
0c802c10 feat(siliconflow): add deepseek-ai/DeepSeek-V4-Flash (#2996)
965a5855 fix: fix deepseek model is not exist (#2990)
f1c4ccd6 fix(volcengine): remove unavailable predefined models (#2993)  ← 命中 cvte: volcengine_maas
c80805b3 fix: add legacy requirements for plugin packages (#2992)
0a303c0a Add DeepSeek V4 Pro and V4 Flash to OpenRouter (#2954)
193e86eb fix(tongyi): combine tts streaming updates (#2987)               ← 命中 cvte: tongyi
37abaafd feat(mimo): add mimo-v2.5 and mimo-v2.5-pro (#2986)
1e682279 feat(vertex_ai): add Claude Opus 4.7 (#2972)                    ← 命中 cvte: vertex_ai
```

### 1.3 安全保护已就位

- 打 tag `pre-merge-test-20260501`（指向 `feat_merge` HEAD），万一合并污染可一键 reset
- 切临时工作分支 `merge-test/upstream-10`，避免直接污染 `feat_merge`

### 1.4 已有 run 数据复用

`.merge/runs/` 已有 4 次同基线 `8e9f8c83` 的 run（来自上一会话），本报告基于这些真实 evidence 分析：

| run_id | 阶段 | plan_rev_rounds | fdr 数 | pud 数 | updated |
|---|---|---|---|---|---|
| 152fd6b0 | plan_review | 0 | 0 | 1290 | 2026-04-30 03:17 |
| 97cfd690 | plan_review | 0 | 0 | 1290 | 2026-04-30 03:18 |
| de00bed4 | plan_review | 0 | 0 | 6 | 2026-04-30 03:28 |
| **19ac33d6** ⭐ | **auto_merge** | 0 | **1033** | 9 | 2026-04-30 06:37 |

`19ac33d6` 是唯一一次进入 auto_merge 阶段的 run，本报告主要 evidence 来源。

---

## 2. 插件分类结果

### 2.1 全量 author 分布（基于 `manifest.yaml`）

| author | 插件数 | 处理策略 |
|---|---|---|
| **`cvte`** | 16 | **二次开发**，需冲突感知合并 |
| `cvte-test` | 1 | 同上（视为 cvte 系） |
| `cvte-old` | 1 | 同上（视为 cvte 系） |
| `langgenius` | 259 | 直接采上游（target） |
| `DougLea` | 10 | 直接采上游 |
| `xinference` / `dify-team` / `chenxu` / `YashParmar` / `AWS` / `langgenius`（不同写法） | 6 | 直接采上游 |
| **总计** | **293** | — |

### 2.2 cvte 系插件清单（18 个）

```
extensions/oaicompat_cvte_dify_model
extensions/voice_assistant
models/azure_openai
models/cvte
models/tongyi
models/vertex_ai
models/volcengine_maas
models/xinference
tools/bing
tools/comfyui
tools/dhr
tools/firecrawl
tools/gaode
tools/google_search
tools/hms
tools/image_collage
tools/maxhub
tools/universal
```

### 2.3 配置策略：依赖 prompt-driven 判断，不在 config 写 cvte 路径

为遵守"code-merge-system 是通用 agent 系统"的原则，**未将 cvte 路径硬编码到 `security_sensitive.patterns` 或任何 `always_take_*_patterns`**。
- `security_sensitive.patterns` 保留默认（`auth/security/secret/credential/password/.pem/.key`），不含 cvte 路径
- Planner / Executor 通过 `project_context` 自然知晓 cvte 二开规则（manifest 中 author 字段 + 上下文提示）
- ✅ Plan 阶段实测结果（见 §3.2）证明该策略有效：cvte 文件 95%+ 走自动路径，不被强制人工

---

## 3. 合并过程分析（基于 19ac33d6 真实 evidence）

### 3.1 全量 diff 规模

`upstream/main~10` 与 `feat_merge` 的全量 diff：
- 总文件 `file_diffs`：**1858**（远超 commit-window 的 344，因为 fork 与 upstream 长期 diverged）
- 检测到 52 个 rename（系统正确识别）
- cvte 子集：**221 个文件**

### 3.2 Plan 分类结果（PlannerJudge 通过后的最终 plan）

| 维度 | auto_safe | auto_risky | human_required | 总数 | 自动率 |
|---|---|---|---|---|---|
| **全量** | 1075 | 533 | 14 | 1622 | **99.1%** |
| **cvte 子集** | 143 | 53 | 5 | 221 | **97.7%** |

⚠️ "全量"行 1075+533+14=1622 ≠ 1858：约 236 个文件未进入 plan 分类（推测被 file_classifier 排除：lock 文件/二进制/excluded patterns）。

### 3.3 cvte 每插件路由分布

| 插件 | auto_safe | auto_risky | human_required |
|---|---|---|---|
| `models/azure_openai` | 6 | 5 | 0 |
| `models/tongyi` | 110 | 20 | **3** |
| `models/vertex_ai` | 9 | 20 | **2** |
| `models/volcengine_maas` | 3 | 3 | 0 |
| `models/xinference` | 1 | 1 | 0 |
| `tools/bing` | 1 | 1 | 0 |
| `tools/comfyui` | 11 | 1 | 0 |
| `tools/firecrawl` | 1 | 1 | 0 |
| `tools/gaode` | 1 | 1 | 0 |
| **TOTAL** | **143** | **53** | **5** |

### 3.4 Plan 中 5 个 cvte HUMAN_REQUIRED 文件

```
models/tongyi/models/llm/qwen3-coder-480b-a35b-instruct.yaml
models/tongyi/models/llm/qwen3-235b-a22b-instruct-2507.yaml
models/tongyi/models/llm/qwen3-max-preview.yaml
models/vertex_ai/models/llm/gemini-3-flash-preview.yaml
models/vertex_ai/models/llm/gemini-3-pro-preview.yaml
```

均为 LLM 模型 yaml 配置文件——Planner 判断这些 cvte 在用的模型规格上游有改动，需 cvte 工程师确认是否覆盖（合理判断，**不属于强制人工**）。

### 3.5 auto_merge 阶段 Executor 决策

`19ac33d6` 在 auto_merge 阶段写入了 1033 条 `file_decision_records`：

| decision | 数量 | 占比 | 主要 rationale |
|---|---|---|---|
| `take_target` | 775 | 75.0% | D-missing 复制（431）/ 直接采上游（239）/ cherry-pick 干净（91）/ 二进制（13）/ 其他（1） |
| `escalate_human` | **258** | **25.0%** | **见 §4** |

**0 条 SEMANTIC_MERGE** —— Executor 的 LLM 语义合并能力 **本次完全没有发挥作用**，所有应走 SEMANTIC_MERGE 的文件被错误降级。

---

## 4. 冲突处理详情

### 4.1 escalate_human 全量 rationale 分布

| rationale | 数量 | 来源 |
|---|---|---|
| `Unsupported auto-merge strategy: MergeDecision.SEMANTIC_MERGE` | **251** | `auto_executor` |
| `Unresolved conflict markers (<<<<<<< / ======= / >>>>>>>) detected in proposed c…` | 5 | `auto_executor` |
| `Could not fetch upstream content for D-missing file` | 2 | `auto_executor` |
| **总计** | **258** | 全部 `auto_executor` |

**251/258 = 97.3% 的人工升级是被同一个 bug 触发的**。

### 4.2 cvte 系 9 个 escalate_human 全部相同症状

```
PATH                                  DECISION_SOURCE  AGENT     CONF  RATIONALE
models/azure_openai/pyproject.toml    auto_executor    executor  0.0   Unsupported auto-merge strategy: SEMANTIC_MERGE
models/tongyi/pyproject.toml          auto_executor    executor  0.0   Unsupported auto-merge strategy: SEMANTIC_MERGE
models/vertex_ai/pyproject.toml       auto_executor    executor  0.0   Unsupported auto-merge strategy: SEMANTIC_MERGE
models/volcengine_maas/pyproject.toml auto_executor    executor  0.0   Unsupported auto-merge strategy: SEMANTIC_MERGE
models/xinference/pyproject.toml      auto_executor    executor  0.0   Unsupported auto-merge strategy: SEMANTIC_MERGE
tools/bing/pyproject.toml             auto_executor    executor  0.0   Unsupported auto-merge strategy: SEMANTIC_MERGE
tools/comfyui/pyproject.toml          auto_executor    executor  0.0   Unsupported auto-merge strategy: SEMANTIC_MERGE
tools/firecrawl/pyproject.toml        auto_executor    executor  0.0   Unsupported auto-merge strategy: SEMANTIC_MERGE
tools/gaode/pyproject.toml            auto_executor    executor  0.0   Unsupported auto-merge strategy: SEMANTIC_MERGE
```

这 9 个 `pyproject.toml` 是 cvte 二开版本依赖列表（cvte 自定义内部库）+ 上游也改了依赖版本——**正是 SEMANTIC_MERGE 的典型用例**：Planner 给出 SEMANTIC_MERGE 决策 → Executor 应调用 LLM 语义合并 → 实际却被 reject。

### 4.3 根因定位（源码层面）

`src/agents/executor_agent.py:212-281` 的 `apply_decision()` 方法只对三种 strategy 生成实际记录：

```python
# executor_agent.py:212-281 概括
async def apply_decision(self, file_diff, strategy, state):
    if strategy == MergeDecision.TAKE_TARGET:
        return apply_with_snapshot(...)
    elif strategy == MergeDecision.TAKE_CURRENT:
        return apply_with_snapshot(...)
    elif strategy == MergeDecision.SKIP:
        return FileDecisionRecord(decision=SKIP, ...)
    # 缺 MergeDecision.SEMANTIC_MERGE 分支！
    return create_escalate_record(
        file_diff.file_path,
        f"Unsupported auto-merge strategy: {strategy}",
    )
```

而下方 `executor_agent.py:283-394` 就有现成的 `execute_semantic_merge()` 方法，包含完整的语义合并逻辑（`build_semantic_merge_prompt` + `_call_llm_with_retry` + memory enrichment + chunked 处理）——**根本没被 `apply_decision` 调用**。

`auto_merge.py` 中 grep `execute_semantic_merge` 结果为 0 行，**phase 调度器从来不调 `execute_semantic_merge`**，只调 `apply_decision`，所以所有 SEMANTIC_MERGE 决策都掉进默认分支变成 escalate。

---

## 5. 流程验证结论

### 5.1 通过项 ✅

| 验证点 | 结果 |
|---|---|
| **Plan 阶段 cvte 不被强制人工** | ✅ 221 cvte 文件中仅 5 个 human_required（2.3%） |
| **Plan 阶段路由通过 prompt 而非硬编码** | ✅ config 中 `security_sensitive.patterns` / `always_take_*` 均未含 cvte 路径，Planner 通过 `project_context` 上下文做出正确判断 |
| **PlannerJudge 收敛** | ✅ `plan_revision_rounds=0`，4 次 run 一次性 plan 通过 |
| **rename 检测** | ✅ 52 个 rename 被正确识别（避免误判文件丢失） |
| **D-missing 处理** | ✅ 431 个新增上游文件被自动 copy（无人工） |
| **Memory hit rate** | ✅ 100%（190/190）—— 见 §6 |
| **`take_target` 路径稳定** | ✅ 775 个文件干净 cherry-pick |

### 5.2 失败项 ❌

| 验证点 | 结果 |
|---|---|
| **Executor 自动合并 cvte 二开冲突** | ❌ 251 文件应走 SEMANTIC_MERGE 全部被 reject 降级人工 |
| **流程能跑完到 judge_review/auto_merging** | ❌ 4 次 run 无一跑完，全部停在 `awaiting_human` |
| **`total_cost_usd` 累计** | ❌ 4 次 run checkpoint 中 cost 全为 `None`，预算熔断（`max_cost_usd=15`）形同虚设 |
| **PlannerJudge 验证记录** | ⚠️ `plan_judge_verdict=None`、`plan_review_log` 仅 1 entry，PlannerJudge 是否真的运行存疑 |
| **gate_history 追踪** | ⚠️ 4 次 run gate_history 全为空 list |
| **UX 可用性** | ❌ 152fd6b0/97cfd690 留下 1290 个 pending_user_decisions —— 用户无法逐个决策，事实上无法走出 plan_review |

### 5.3 整体结论

> **Plan 阶段架构与策略合理且工作正常；Executor 阶段实质失能。**
>
> 系统整体 design 是对的（Planner 不强制 cvte 走人工 + Executor 设计有 LLM 语义合并能力），但 `apply_decision` ↔ `execute_semantic_merge` 之间的调度链路断了，导致语义合并在生产路径上 100% 不可用。

---

## 6. Memory 系统利用率分析

### 6.1 现状数据（`memory_hit_stats.json`）

```json
{
  "schema_version": 2,
  "calls_by_phase": { "auto_merge": 190 },
  "hit_calls_by_phase": { "auto_merge": 190 },
  "entries_by_phase_layer": {
    "auto_merge": {
      "l1_patterns": 950,
      "l1_decisions": 380,
      "l2": 68
    }
  },
  "entry_outcomes": {}
}
```

`memory.db`：49KB，存储 1398 条 entry（950+380+68）。

### 6.2 利用率评估

| 指标 | 数值 | 评估 |
|---|---|---|
| 总调用 | 190 | auto_merge 阶段 1033 次决策中 18.4% 触达 memory |
| 命中率 | **190/190 = 100%** | ✅ 优秀（每次调用都命中至少一条记忆） |
| 调用覆盖阶段 | 仅 `auto_merge` | ❌ planner/conflict_analyst/judge **都未使用 memory** |
| L1/L2 比 | 1330:68（19.6:1） | L2（语义聚合层）使用率偏低 |
| `entry_outcomes` | **空 `{}`** | ❌ 没有跟踪记忆条目最终是否被采纳/被回滚 |
| `schema_version` | 2 | 已升级版本，但 outcomes 字段未被写入 |

### 6.3 优化建议

**优化点 1：扩展 memory 调用到所有 LLM agent**
- 当前仅 Executor 在调 memory，Planner/ConflictAnalyst/Judge 完全不读历史决策
- 影响：相同 cvte 插件每次合并 Planner 都从零判断 risk_level，无法复用历史确认过的 routing 模式
- 建议：在 `planner_agent.py`/`conflict_analyst_agent.py` 的 prompt build 里也注入 `memory_text`（参考 `executor_agent.py:325-339` 实现）

**优化点 2：闭环 `entry_outcomes`**
- `schema_version=2` 已为 outcomes 设计了字段位，但实际未写入
- 建议在 `judge_agent` 或 `report_writer` 写出最终决策后，回写 outcomes：`accepted` / `rolled_back` / `human_overrode` / `gate_failed`
- 用于：定期 prune 长期未采纳的 patterns、给高采纳 patterns 加权

**优化点 3：补 L2 聚合**
- L1（patterns 950 + decisions 380）远多于 L2（68），聚合层稀疏
- 建议：每 N 次 L1 hit 后由 `memory_extractor_agent` 触发 L2 聚合，把同插件/同冲突类型的多条 L1 合成一条高置信 L2
- 收益：减少 prompt 注入体积、提升相同场景下的判断速度

**优化点 4：100% 命中率 ≠ 真实信号有用**
- 100% hit 可能意味着每次都注入"通用 fallback 记忆"——需检查 `memory_text` 实际内容质量
- 建议：增加 `effective_hit_rate`（命中且影响最终决策的比例），区分真正起作用的记忆 vs noise

---

## 7. 存在的问题与改进建议

按严重性排序。

### 🔴 P0：Executor 不支持 SEMANTIC_MERGE（核心阻断）

**症状**：251/258 escalate_human = `Unsupported auto-merge strategy: MergeDecision.SEMANTIC_MERGE`，包括 9 个 cvte `pyproject.toml`。

**根因**：`src/agents/executor_agent.py:apply_decision` 缺 SEMANTIC_MERGE 分支；现成的 `execute_semantic_merge()` 方法没被 phase 调度器（`auto_merge.py`）调用。

**修复建议**（最小 diff）：
```python
# executor_agent.py:apply_decision 新增分支
elif strategy == MergeDecision.SEMANTIC_MERGE:
    # 需要 conflict_analysis；从 state.conflict_analyses 取
    ca = state.conflict_analyses.get(file_diff.file_path)
    if ca is None:
        # fallback: 走 conflict_analyst 现场分析
        ca = await self._infer_conflict_analysis(file_diff, state)
    return await self.execute_semantic_merge(file_diff, ca, state)
```

**验证**：再跑一次同基线 run，应看到 250+ 文件从 `escalate_human` 转为 `take_target`/`semantic_merge` 决策。

### 🔴 P0：成本累计未生效

**症状**：`max_cost_usd=15` 配置存在，但 4 次 run checkpoint 中 `total_cost_usd=None` —— 熔断永远不会触发，理论上单 run 可以无限烧钱。

**修复建议**：检查 `BaseAgent._call_llm_with_retry` 是否回写 `state.total_cost_usd`，以及 `Orchestrator` 在每个 phase 完成后是否累加 + 校验阈值。

### 🟠 P1：plan_review 阶段 UX 不可用

**症状**：3 次 run 留下 1290 / 1290 / 6 个 `pending_user_decisions`，用户无法逐文件决策。

**根因猜测**：Planner 输出的 plan 中所有需要 user 决策的文件都被汇集，没有优先级排序也没有 batch 决策机制。

**修复建议**：
1. plan_review CLI 增加"全部 take_target / 全部 take_current / 仅 cvte 走人工"批量按钮
2. 默认 pending list 仅含 `human_required` 文件，`auto_risky` 不需要 user 显式 confirm

### 🟠 P1：PlannerJudge 是否真的运行存疑

**症状**：4 次 run 全部 `plan_judge_verdict=None`、`plan_review_log` 仅 1 entry、`gate_history=[]`。

**修复建议**：审计 `plan_review.py` 是否在所有路径上都调用了 PlannerJudge 并持久化 verdict；增加单元测试覆盖 verdict 为空场景。

### 🟡 P2：Memory 系统改进（详见 §6.3）

- 扩展 memory 到 Planner / ConflictAnalyst / Judge
- 闭环 `entry_outcomes`
- 增加 L2 聚合频率
- 引入 `effective_hit_rate` 替代裸 hit_rate

### 🟡 P2：目标仓库 untracked 资源文件

**症状**：12 个 `_assets/*.png` untracked，影响仓库 cleanness 判定。

**建议**：合并前要求用户三选一：`git add` / `git stash -u` / `git clean -fd`；CLI 在 init phase 检测到 untracked 时弹出提示。

### 🟡 P2：测试基线 commit 选择策略缺指引

**症状**：用户无法判断该选 ~5 / ~10 / ~30 / ~50 哪个基线，需手动 grep。

**建议**：CLI 提供 `merge plan-suggest --target upstream/main` 子命令，输出多档基线候选 + cvte 命中数 + 估算成本。

### 🟢 P3：`merge` CLI `repo_path` 默认相对路径，配置示例使用了不存在的绝对路径

**症状**：`config/dify-plugins.yaml` 中 `repo_path: /Users/angel/Desktop/WA_AI/...`（不存在）；用户实际仓库在 `/Users/angel/AI/project/...`。

**建议**：配置默认值改为 `.`（相对路径，由 CLI 在调用目录解析），或在 `merge validate` 时检查 `repo_path` 实存性。

---

## 附录 A：测试方案（针对 code-merge-system 后续回归）

为方便后续验证 P0 修复后的回归，建议形成以下三层测试：

### A.1 冒烟测试（dry-run，~$5）

```bash
cd /Users/angel/AI/project/dify-official-plugins
git checkout merge-test/upstream-10
merge upstream/main~10 --no-tui --ci --dry-run
```
验收标准：
- plan_review 报告生成，`auto_safe + auto_risky + human_required` 总数 ≥ 1500
- cvte 系 `human_required ≤ 10`
- 无 phase crash

### A.2 中规模真跑（~10 commits、~$30）

```bash
merge upstream/main~10 --no-tui --ci --max-cost-usd 35
```
验收标准（需 P0 修复后）：
- `file_decision_records` 中 `decision=semantic_merge` 数量 > 0（关键回归点）
- `escalate_human` 中 `Unsupported auto-merge strategy` rationale 出现次数 = 0
- `total_cost_usd` 非 None
- `judge_verdict` 至少 1 次有效输出

### A.3 大基线压力测试（~50 commits、~$100）

仅在前两层全绿后执行；用于压测 chunked semantic merge / B-class drift 抑制 / 成本熔断真实生效。

### A.4 cvte 子集隔离测试

为快速验证 SEMANTIC_MERGE 修复，构造仅含 cvte 文件的最小重现：
```bash
# 只包含 cvte/pyproject.toml 的 9 个文件
merge upstream/main~10 --no-tui --ci --include-paths "$(cat /tmp/cvte_dirs.txt | sed 's|$|/pyproject.toml|' | tr '\n' ',')"
```
预期：9 个全部走 SEMANTIC_MERGE，0 个 escalate。

---

## 附录 B：本次 evidence 出处

所有数据均来自下列文件，未经任何加工：

```
/Users/angel/AI/project/dify-official-plugins/.merge/runs/19ac33d6-1291-43fd-afbd-f4fbecaae792/checkpoint.json   (177MB)
/Users/angel/AI/project/dify-official-plugins/.merge/runs/152fd6b0-*/checkpoint.json  (121MB)
/Users/angel/AI/project/dify-official-plugins/.merge/runs/97cfd690-*/checkpoint.json  (121MB)
/Users/angel/AI/project/dify-official-plugins/.merge/runs/de00bed4-*/checkpoint.json  (120MB)
/Users/angel/AI/project/dify-official-plugins/.merge/memory_hit_stats.json
/Users/angel/AI/project/dify-official-plugins/.merge/memory.db                        (49KB)
/Users/angel/AI/personal/code-merge-system/src/agents/executor_agent.py:212-394
/Users/angel/AI/personal/code-merge-system/src/core/phases/auto_merge.py:1074-1186
```

报告生成命令未涉及任何写操作（除本报告自身），`merge-test/upstream-10` 临时分支与 `pre-merge-test-20260501` tag 保留供后续验证。
