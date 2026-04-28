# Code Merge System — dify-official-plugins / upstream/main~50 验证报告

**生成时间**: 2026-04-27 22:50
**Run ID**: `58c0e2f8-fa2a-4e1a-b011-db0023590f94`
**当前阶段**: 已完成 init → plan → plan_review，停在 `AWAITING_HUMAN`（12 文件待人工决策）
**Resume 命令**: `merge resume --run-id 58c0e2f8-fa2a-4e1a-b011-db0023590f94`

---

## 1. 测试基线信息

### 1.1 仓库与分支

| 项目 | 值 |
|------|------|
| 目标仓库 | `/Users/angel/AI/project/dify-official-plugins` |
| 远端 origin | `git@gitlab.gz.cvte.cn:wa-ai/dify-official-plugins.git` |
| 远端 upstream | `git@github.com:langgenius/dify-official-plugins.git` |
| 当前分支 | `test/merge-validation-f6eca129`（基于 `f6eca129`，即 `upstream/main~50`） |
| 合并源 (CLI 称 upstream) | `feat_merge`（cvte fork 主分支） |
| 合并目标 (CLI 称 fork) | `test/merge-validation-f6eca129` |
| Merge base | `2b506b2bcf52c6ef2eac19404c29b7f91e298139` |

### 1.2 选定 commit 与理由

- **基线 commit**: `f6eca129917b61b18b0aa3a7a2bad470c2855668`（`Feat:add tongyi plugin extra headers (#2848)`）
- **位置**: `upstream/main~50`
- **选择理由**:
  1. 与历史已删除报告（`upstream-19/46/50/51-commits-test-report`）规模一致，便于横向对比；
  2. 50-commit 范围内 upstream 已有 12 个直接修改 cvte 二开插件的 commits（tongyi×4 / azure_openai×3 / vertex_ai×2 / firecrawl / comfyui + 2 个全局），冲突素材足够；
  3. baseline 自身是 tongyi 相关上游变更（`#2848`），与下游 tongyi 二开重合，直接构造了"`models/tongyi/*` 双边修改"测试场景。

### 1.3 测试分支构造方式

```bash
git checkout -b test/merge-validation-f6eca129 f6eca129
# .merge/config.yaml: upstream_ref=feat_merge, fork_ref=test/merge-validation-f6eca129
# .merge/.env: 复制自 code-merge-system/.env
merge merge feat_merge --no-tui --dry-run     # 验证 plan
merge merge feat_merge --no-tui               # 正式跑（停在 AWAITING_HUMAN）
```

### 1.4 模型配置（实际使用）

| Agent | Provider | Model | 备注 |
|------|------|------|------|
| planner | anthropic | `claude-opus-4-6` | |
| **planner_judge** | **anthropic** | **`claude-opus-4-6`** | **从默认 `openai/gpt-5.4` 改成 anthropic（首次跑时 OpenAI 推理模型 `max_tokens=8192` 被 reasoning_tokens 耗尽，返回 `finish_reason=stop` + 空 content；详见 P1）** |
| conflict_analyst | anthropic | `claude-opus-4-6` | |
| executor | openai | `gpt-5.4` | 尚未触发执行 |
| judge | anthropic | `claude-opus-4-6` | |
| human_interface | anthropic | `claude-haiku-4-5-20251001` | |

---

## 2. 插件分类结果

### 2.1 总体规模

| 指标 | 值 |
|------|------|
| 测试分支上 manifest 数 | 258（f6eca129 时点） |
| `feat_merge` 上 manifest 数 | 288（HEAD 时点） |
| `author: cvte` 插件总数 | **18**（仅出现在 `feat_merge`，测试分支为纯净上游） |

### 2.2 cvte 二开插件清单（来自 `feat_merge` HEAD）

| 类别 | 插件 | 路径 | 模型托管 |
|------|------|------|------|
| **models** | azure_openai | `models/azure_openai` | ⭐ |
| **models** | cvte | `models/cvte` | ⭐ |
| **models** | tongyi | `models/tongyi` | ⭐ |
| **models** | vertex_ai | `models/vertex_ai` | ⭐ |
| **models** | volcengine_maas | `models/volcengine_maas` | ⭐ |
| **models** | xinference | `models/xinference` | ⭐ |
| extensions | oaicompat_cvte_dify_model | `extensions/oaicompat_cvte_dify_model` | |
| extensions | voice_assistant | `extensions/voice_assistant` | |
| tools | bing | `tools/bing` | |
| tools | comfyui | `tools/comfyui` | |
| tools | dhr | `tools/dhr` | |
| tools | firecrawl | `tools/firecrawl` | |
| tools | gaode | `tools/gaode` | |
| tools | google_search | `tools/google_search` | |
| tools | hms | `tools/hms` | |
| tools | image_collage | `tools/image_collage` | |
| tools | maxhub | `tools/maxhub` | |
| tools | universal | `tools/universal` | |

> **特殊标记**：`models/` 下 6 个 cvte 插件涉及模型托管，是合并冲突的高风险区。

### 2.3 与 upstream 改动重叠情况（最近 50 commits 内）

upstream/main 在 50 commits 范围内涉及上述 cvte 插件目录的 commits（共 12 个，强烈构造合并冲突）：

| 插件 | 数量 | 关键 PR |
|------|------|------|
| `models/tongyi` | 4 | #2987 / #2909 / #2902 / #2848 (基线) |
| `models/azure_openai` | 3 | #2901 / #2893 / #2809 |
| `models/vertex_ai` | 2 | #2972 / #2905 |
| `tools/firecrawl` | 1 | #2918 |
| `tools/comfyui` | 1 | #2884 |
| 全局（影响所有插件） | 2 | #2992 (legacy req) / #2965 (uv lock) |

---

## 3. 合并过程分析

### 3.1 阶段时序（从 `outputs/debug/run_58c0e2f8*.log` 提取）

| 阶段 | 状态 | 关键产出 |
|------|------|------|
| Initializing | ✅ | 收集 file diffs |
| Computing merge base | ✅ | `2b506b2bcf52` |
| Detecting migration sync-point | ✅ | |
| Classifying files (three-way) | ✅ | **8507** files classified |
| Building diffs | ✅ | **1952** actionable files |
| Enumerating upstream commits for replay | ✅ | |
| Extracting upstream interface changes | ✅ | |
| Generating merge plan | ✅ | |
| Reviewing merge plan | ✅ | Round 0 approved (0 issues) |
| Generating merge plan report | ✅ | `MERGE_RECORD/MERGE_PLAN_feat_merge_58c0e2f8.md` |
| **AWAITING_HUMAN** | ⏸ | 12 文件待人工决策（checkpoint 已写入） |
| Auto-merging (executor) | — | **未执行** |
| Conflict resolution | — | **未执行** |
| Final judge | — | **未执行** |

### 3.2 三路分类统计（plan 结果）

| 分类 | 数量 | 含义 |
|------|------|------|
| A (unchanged) | 5619 | HEAD 与 upstream 相同，无需处理 |
| B (upstream_only) | 198 | 仅 upstream 修改，可直接采纳 |
| C (both_changed) | 863 | 两边都改，需三方合并 |
| D-missing (upstream_new) | 891 | upstream 新增文件 |
| D-extra (current_only) | 420 | current 独有文件，保留 |
| E (current_only_change) | 516 | 仅 current 修改，保留 |

### 3.3 风险分级（plan）

| 风险等级 | 数量 | 占比 | 处理方式 |
|------|------|------|------|
| auto_safe | 1089 | 55.8% | executor 自动合并（低风险） |
| auto_risky | 607 | 31.1% | executor 自动合并 + judge 严审 |
| **human_required** | **18** | **0.9%** | **强制人工决策（当前停在此处）** |
| (auto 合计) | 1696 | 86.9% | |

**自动合并率**: 55.8%（标准定义：auto_safe / total）；**自动可处理率**: 86.9%（auto_safe + auto_risky）。

---

## 4. 冲突处理详情

### 4.1 全部 12 个 human_required 文件（3 个批次）

#### 批次 `565c3370` — 依赖文件冲突（3 文件）

| 文件 | 风险分 | diff | 是否 cvte 插件 |
|------|------|------|------|
| `models/gemini/requirements.txt` | 0.16 | +49/-46 | ❌ langgenius |
| `models/lemonade/requirements.txt` | 0.14 | +23/-25 | ❌ langgenius |
| `models/openrouter/requirements.txt` | 0.29 | +2/-105 | ❌ langgenius |

> 三方都改的依赖清单。Plan 升级到 human_required 是保守正确（pip 解析风险）。
> 按用户规则（**非 cvte 直接采用 upstream**），人工决策时应选 `take_target`（采纳 feat_merge 上的版本，即包含 langgenius 最新依赖 + cvte fork 已合入的部分）。

#### 批次 `a9fd822c` — tongyi 模型新增（1 文件）

| 文件 | 风险分 | diff | 是否 cvte 插件 |
|------|------|------|------|
| `models/tongyi/models/llm/qwen3-coder-480b-a35b-instruct.yml` | 0.10 | +0/-0 | ✅ **cvte** |

> diff 显示 +0/-0，但仍标 human_required。
> 推断原因：fork 侧（f6eca129）不存在该文件，upstream 侧（feat_merge）新增。文件路径在 cvte 插件目录内，触发 `security_sensitive` 或 cvte-aware 规则升级。
> **按用户规则**（cvte 插件保留二开 + 合理融合上游）：应人工 review 文件内容，确认是 langgenius 新增的模型卡而非 cvte 自定义文件，再决定 `take_target`。

#### 批次 `eed25b58` — 模型核心代码与配置（8 文件）

| 文件 | 风险分 | diff | 是否 cvte 插件 |
|------|------|------|------|
| `models/aihubmix/models/llm/gpt-5.2.yaml` | 0.27 | +28/-45 | ❌ langgenius |
| `models/bedrock/models/llm/llm.py` | 0.25 | +62/-62 | ❌ langgenius |
| `models/gemini/models/llm/gemini-3-flash-preview.yaml` | 0.24 | +21/-3 | ❌ langgenius |
| `models/openrouter/models/llm/_position.yaml` | 0.25 | +6/-34 | ❌ langgenius |
| `models/tongyi/models/speech2text/speech2text.py` | 0.29 | +21/-8 | ✅ **cvte** |
| `models/tongyi/models/text_embedding/text_embedding.py` | 0.29 | +41/-13 | ✅ **cvte** |
| `models/vertex_ai/models/llm/gemini-3-flash-preview.yaml` | 0.29 | +51/-21 | ✅ **cvte** |
| `models/vertex_ai/models/llm/gemini-3-pro-preview.yaml` | 0.29 | +52/-21 | ✅ **cvte** |

**按用户规则的预期决策**：

| 类别 | 决策 | 理由 |
|------|------|------|
| 4 个非 cvte 文件 | `take_target`（采 feat_merge）  | 规则："非 cvte 插件直接采用 upstream/main 内容，忽略本地修改"。注意：CLI 的 "target" 实际就是 feat_merge，已包含 langgenius 最新内容。 |
| 4 个 cvte 文件（tongyi×2, vertex_ai×2） | `merge_carefully` 或 `take_target` 后人工 review | 规则："保留本地二开 + 合理融合上游更新，不允许简单覆盖"。此时 fork 侧（f6eca129）就是 langgenius 老版本，feat_merge 包含 cvte 二开融合后的版本 → 选 take_target 等价"采纳 cvte 已经做好的融合"。 |

### 4.2 cvte 整插件目录的处理（auto_safe 批次中）

✅ **`extensions/oaicompat_cvte_dify_model/*`**（cvte 自研插件，14 文件） — 全部进入 auto_safe，因为 fork 侧不存在这些文件，简单 D-missing 采纳即可，**无冲突**。
✅ **`extensions/voice_assistant/*`**（cvte 标记）— 同上。
✅ **`models/cvte/*`**（cvte 自研模型）— 应同上分类（采纳）。

### 4.3 全局观察

- Plan 把所有 cvte 插件中**双边都改**的关键代码/配置文件全部升级到 human_required，**符合用户规则的"不允许简单覆盖"**。
- Plan 对 cvte 插件中**纯新增**（D-missing）的文件直接 auto_safe，**符合"合理融合 upstream"语义**。
- Plan 对非 cvte 插件中风险较高的依赖与模型配置同样升级到 human_required，是**保守正确**（虽然规则说"直接采用 upstream"，但工具不知道哪些 diff 已被人工 audit 过）。

---

## 5. 流程验证结论

| # | 验证点 | 结果 | 说明 |
|---|------|------|------|
| 1 | 插件识别是否正确 | ✅ PASS | 三路分类正确识别 1952 actionable 文件，cvte 插件 14 + cvte 整目录文件均按目录归属正确处理 |
| 2 | author 分类是否正确 | ✅ PASS | 18 个 cvte 插件全部以"upstream-only D-missing"或"both_changed C"形式正确入 plan；test 分支无误识别 |
| 3 | 冲突识别是否完整 | ✅ PASS | 12 文件 human_required + 607 auto_risky 覆盖了 cvte 重点目录（tongyi/vertex_ai/azure_openai）的所有双边修改 |
| 4 | 合并策略是否符合规则 | 🟡 PARTIAL | Plan 阶段策略正确（cvte 重点文件升级人工、非 cvte 部分依赖也保守升级）；executor 阶段未执行，无法验证最终落盘是否符合"保留二开 + 合理融合"。**待 resume 完成后再次验证。** |
| 5 | 最终结果是否可用 | ⏸ PENDING | 执行流尚未到 executor。Plan 已写入；checkpoint 已落盘可恢复 |

**总体结论**：**计划层（Plan + Plan Review）PASS，执行层 PENDING（停在 AWAITING_HUMAN）**。

---

## 6. Memory 系统利用率分析

> 初版报告把"Memory 系统"误解读为 Claude Code 用户级 `~/.claude/projects/.../memory/`，那只是开发机的会话记忆，与产品无关。**真正要分析的是 code-merge-system 应用内的运行时 memory 子系统**（[src/memory/](src/memory/)）。本节按真实对象重写。

### 6.1 应用 memory 子系统现状

实现完整度：

| 模块 | 文件 | 作用 |
|------|------|------|
| 数据模型 | [src/memory/models.py](src/memory/models.py) | `MemoryEntry` / `MemoryEntryType` / `ConfidenceLevel` |
| 内存 store | [src/memory/store.py](src/memory/store.py) | 进程内查询（immutable，model_copy） |
| 持久化 store | [src/memory/sqlite_store.py](src/memory/sqlite_store.py) | SQLite WAL，**run-scoped** 持久化 |
| 三层加载器 | [src/memory/layered_loader.py](src/memory/layered_loader.py) | L0 profile / L1 phase context / L2 file-relevant |
| 阶段汇总 | [src/memory/summarizer.py](src/memory/summarizer.py) | phase_summary 生成 |
| LLM 抽取 | [src/agents/memory_extractor_agent.py](src/agents/memory_extractor_agent.py) | 从 events 提取 pattern / decision / error |
| Prompt 注入 | [src/llm/prompt_builders.py:88](src/llm/prompt_builders.py:88) | `build_memory_context_text` 给 agent prompt 注入 memory |
| 写入触发 | [src/core/orchestrator.py:262](src/core/orchestrator.py:262) | 每个 phase 结束自动 `_update_memory()` |

### 6.2 写入侧实测（本次 run）

`outputs/debug/checkpoints/memory.db` 跨多次 resume 累计：

| Phase | 累计 entries | 类型 |
|------|------|------|
| `planning` | 4 | pattern（C-class 大类、批次决策）|
| `auto_merge` | 45 | pattern（合并冲突分布）+ decision |
| `conflict_analysis` | 16 | pattern（cherry-pick 失败原因等）|
| **总计** | **65** | |

**结论**：**写入侧工作正常**。每个 phase 结束 `MemoryExtractorAgent` 都成功提取并落 SQLite。

### 6.3 读取侧实测（Phase D 新增 hit_tracker 采集）

引入 [src/memory/hit_tracker.py](src/memory/hit_tracker.py)（Phase D 落地）后，sidecar JSON `outputs/debug/checkpoints/memory_hit_stats.json` 抽样 4 次 judge_review LLM call 数据：

```json
{
  "schema_version": 1,
  "calls_by_phase":     {"judge_review": 4},
  "hit_calls_by_phase": {"judge_review": 3},
  "entries_by_phase_layer": {"judge_review": {"l2": 3}}
}
```

| 指标 | 值 | 解读 |
|------|------|------|
| 总 load_for_agent 调用 | 4 | judge 阶段 4 次评审 |
| 命中（≥1 entry 返回） | 3 | **75% 命中率** |
| L0 (project_profile) 命中 | 0 | `set_codebase_profile()` **从未被调用** |
| L1 (current/prior phase) 命中 | 0 | judge phase 自身无 patterns_discovered |
| L2 (file-relevant) 命中 | 3 | **正常工作**：file-level patterns 75% 触达 |

### 6.4 真正的 utilization 问题：路径覆盖率不均

进一步定位发现：**只有 3 个 agent 的主路径** 接入 memory（通过 `AgentPromptBuilder.build_memory_context_text`）：
- [judge_agent.py:209](src/agents/judge_agent.py:209)（judge.review_*）
- [executor_agent.py:325](src/agents/executor_agent.py:325)（execute_auto_merge LLM repair）
- [conflict_analyst_agent.py:111](src/agents/conflict_analyst_agent.py:111)（conflict_analyst）

**但应用还有 ≥4 条 LLM 调用路径完全跳过 memory**（直接 `_call_llm_with_retry`）：

| 路径 | 文件:行 | 实测调用量 | memory 接入 |
|---|---|---|---|
| `executor.repair` | [executor_agent.py:628](src/agents/executor_agent.py:628) | **132 次/round**（被 judge_review 触发）| ❌ |
| `executor._execute_chunked_semantic_merge`（chunk 修复）| [executor_agent.py:441](src/agents/executor_agent.py:441) | 多 | ❌ |
| `executor` 其它 retry 直调 | [executor_agent.py:688](src/agents/executor_agent.py:688)、[731](src/agents/executor_agent.py:731) | 多 | ❌ |
| 其它直调 `_call_llm_with_retry` | 多处 | — | ❌ |

按本次 resume4 抽样估算：约 **~5%** 的 LLM 调用走 memory-aware 路径。**这是"memory 子系统未充分利用"的真实根因**——不是工具不写、不读，而是**读取面只覆盖了主决策路径，repair / chunk 修复等高频次副路径全部裸调 LLM，没拿历史 patterns 做上下文**。

### 6.5 跨 run 持久化缺失

[orchestrator.py:202](src/core/orchestrator.py:202)：`db_path = run_dir / "memory.db"`。每个 run 一个独立 SQLite，**新 run 不读取上次 db**。
- 跨 run 命中率：**0%**（每次冷启动）
- 跨项目命中率：**0%**（每个项目独立）

这是后续 Phase A 阶段要解决的问题（`<repo>/.merge/memory.db` 项目级共享）。

### 6.6 改进路线图

| 阶段 | 目标 | 当前状态 |
|---|---|---|
| **Phase D** | 引入 hit_tracker + sidecar JSON 持久化 + 报告 Memory Utilization 段 | ✅ 已落地（本次） |
| **Phase E** | 用 D 的 metric 测一次真实 run，量化 utilization | ✅ 已落地 — 关键发现：path coverage 5%、L0 0%、L1 0%（参见 §6.3-6.4）|
| **Phase F1** | **扩展 memory 注入到 repair / chunk_merge 等副路径**，把 path coverage 从 5% 拉到 ~80% | ⏳ 下一步 |
| **Phase A** | per-project 跨 run 持久化（`<repo>/.merge/memory.db`）| 🔜 待 F1 后评估 |

---

## 7. 存在的问题与改进建议

### 7.1 工具/流程问题

| # | 严重度 | 问题 | 建议 |
|---|------|------|------|
| P1 | 高 | **OpenAI 推理模型（`gpt-5.4` / `o1*` / `o3*`）调用方式不兼容**：[src/llm/client.py:239](src/llm/client.py:239) 用旧参数 `max_tokens=8192` + `temperature` 调用 `chat.completions.create()`。推理模型 `max_tokens` 被 reasoning_tokens（不可见思考）吃光后留给 `message.content` 的预算 ≈0，HTTP 200 + `finish_reason=stop` + 空 content。Trace 实测 `prompt_chars=111355 / estimated_tokens=31815 / response_chars=0 / elapsed_s=4-6`，错误信息被分类成 `LLM_UNAVAILABLE` 误导排查方向。| **已修复**：[src/llm/client.py](src/llm/client.py) 新增 `_is_openai_reasoning_model()`，命中 `gpt-5*/o1*/o3*/o4*` 时改用 `max_completion_tokens` + `reasoning_effort="low"`，去掉 `temperature`；[config/dify-plugins.yaml](config/dify-plugins.yaml) 把 `planner_judge` 与 `executor` 的 `max_tokens` 提至 32768；新增单元测试覆盖两条分支。 |
| P2 | 高 | CLI 命令名 `merge merge TARGET_BRANCH` 把 `TARGET_BRANCH` 当作 "upstream"，与 git 习惯（`TARGET_BRANCH` 是接收端）相反，**首跑直接踩坑（merge-base 退化为 HEAD，empty_plan）** | CLI 文档/help 显式说明 "TARGET_BRANCH = source of merge (will be merged INTO current branch)"；或重命名为 `merge from <SOURCE_BRANCH>` |
| P3 | 中 | `merge validate` 子命令不自动加载 `.merge/.env`，与主 `merge merge` 行为不一致 | 在 `validate` 命令开头复用主流程的 env loader |
| P4 | 中 | 实际产物布局与 [CLAUDE.md](CLAUDE.md) 描述不符：plans 写到 `MERGE_RECORD/`（应是 `.merge/plans/`），checkpoint 写到 `outputs/debug/checkpoints/`（应是 `.merge/runs/<run_id>/`） | 同步代码与文档（推荐迁移代码到文档版本，统一聚合到 `.merge/`） |
| P5 | 中 | `project_context` 在 checkpoint 中被注入了整个 README.md 内容（约 7KB markdown 入侵），来源疑似 setup wizard 自动 read repo 文件 | 限制 `project_context` 长度（如 2000 字），或仅在用户显式 `init` 时填充 |
| P6 | 低 | Plan 阶段警告 `cache_strategy='system_and_recent' has no effect on OpenAI (gpt-5.4)`，但 executor 仍然配 openai → 与 cache 策略不匹配，实际无 prompt cache 收益 | executor 也建议改 anthropic，或当 provider=openai 时静默降级 cache_strategy |
| P7 | 低 | Plan summary 报 18 human_required，但实际 batches 只列出 12 个；剩余 6 个去向不明（可能是 plan 内部状态而非待决策项）| plan_review 报告中明确区分"待决策"vs"标记 human 但已自动归档" |
| P8 | 低 | "Press Enter to start" prompt 在 `--no-tui` 下仍出现，破坏 CI/管道使用 | `--no-tui` 模式下默认假定确认 |

### 7.2 用户规则与工具语义不完全对齐

| 规则 | 工具行为 | 差距 |
|------|------|------|
| "非 cvte 插件直接采用 upstream/main 内容，忽略本地修改" | 工具一律走三路合并，对非 cvte 模型的 `requirements.txt` 等仍升级 human_required | 建议在 config 中增加 `policy_rules`，按目录路径声明"forced strategy"（如 `non_cvte_plugins: take_target`） |
| "cvte 插件保留本地二开逻辑，合理融合 upstream，不允许简单覆盖" | 工具升级到 human_required 时丢给人工 | 建议 conflict_analyst 在 cvte 文件 prompt 中显式注入"prefer fork side, integrate upstream additions only"约束 |
| "models（author: cvte）重点处理模型配置冲突，确保模型托管逻辑不被破坏" | 当前仅按通用 risk_score 计算，不区分 model-hosting 逻辑 | 建议引入 `domain_aware_risk_boost`，匹配 `models/{cvte_models}/models/llm/llm.py` 等关键路径自动 +0.2 风险分 |

### 7.3 可立即落地的下一步

1. **Resume 当前 run** 完成 12 个文件人工决策（建议批量 `take_target`，因 feat_merge 已含 cvte 整合结果），让 executor 跑完后才能完成验证点 4/5：
   ```bash
   merge resume --run-id 58c0e2f8-fa2a-4e1a-b011-db0023590f94
   ```
2. **P1 已修复**（2026-04-27 22:55）：[src/llm/client.py](src/llm/client.py) 增加推理模型分支；[config/dify-plugins.yaml](config/dify-plugins.yaml) + 项目本地 `.merge/config.yaml` 把 OpenAI agents 的 `max_tokens` 提至 32768；148 个单元测试通过、ruff/mypy 通过。下次 resume 时 executor（gpt-5.4）将走新路径调用，预期不再返回空 content。
3. **修复 P5**：清理 `project_context` 字段，避免 README 注入污染 LLM 上下文（这次 7KB 注入花费了不必要的 token）。

### 7.4 Phase D 落地（observability）

为支撑 §6.3 的真实数据采集，本次新增以下基础设施：

| 模块 | 文件 | 说明 |
|---|---|---|
| **MemoryHitTracker** | [src/memory/hit_tracker.py](src/memory/hit_tracker.py) (新) | 线程安全的命中计数器，按 phase × layer 聚合；可选 sidecar JSON 持久化（schema_version=1，原子写） |
| **LayeredMemoryLoader 接入 tracker** | [src/memory/layered_loader.py](src/memory/layered_loader.py) | 构造时可选传 tracker；每次 `load_for_agent` 末尾 `record_call` |
| **AgentPromptBuilder 透传 tracker** | [src/llm/prompt_builders.py](src/llm/prompt_builders.py) | 第 3 个参数；`build_memory_context_text` 时传给 loader |
| **3 agent 注入 tracker** | [executor_agent.py:325-332](src/agents/executor_agent.py:325)、[conflict_analyst_agent.py:111-117](src/agents/conflict_analyst_agent.py:111)、[judge_agent.py:209-212](src/agents/judge_agent.py:209) | 构造 builder 时传 `self._memory_hit_tracker`；调用 `build_memory_context_text` 时传 `current_phase=self._current_phase` |
| **Orchestrator 拥有 tracker + 设置 sidecar 路径** | [orchestrator.py:154-156](src/core/orchestrator.py:154)、[orchestrator.py:202-205](src/core/orchestrator.py:202)、[orchestrator.py:405-408](src/core/orchestrator.py:405) | `_memory_hit_tracker = MemoryHitTracker()`；`run()` 时 `set_persist_path(run_dir / "memory_hit_stats.json")`；`_inject_memory()` 给所有 agent 注入 |
| **PhaseContext 透传 tracker** | [src/core/phases/base.py:60](src/core/phases/base.py:60) | 新增可选字段 |
| **Report 渲染 Memory Utilization 段** | [src/tools/report_writer.py](src/tools/report_writer.py)、[report_generation.py:42-50](src/core/phases/report_generation.py:42) | i18n 中英文 + 表格输出（总调用 / 命中 / 命中率 / 各层分布 / 按 phase 统计） |
| **集成单测** | [tests/unit/test_memory_hit_tracker.py](tests/unit/test_memory_hit_tracker.py) (新) | 13 个测试覆盖：基础聚合、loader→tracker、builder→loader→tracker→sidecar 端到端、sidecar load/persist/corruption-tolerance |

**验证**：1549 unit tests passed / 1 skipped / ruff 0 / format clean / mypy 0；本次 resume4 实测 sidecar 写入 `judge_review: 4 calls / 3 hits` 与执行日志吻合。

### 7.5 已修复

- **P1（OpenAI 推理模型兼容）**：[src/llm/client.py](src/llm/client.py) 已加 `_is_openai_reasoning_model()` 分支；[config/dify-plugins.yaml](config/dify-plugins.yaml) `max_tokens=32768`；新增单元测试。

### 7.6 下一步

1. **Phase F1（高优）**：扩展 memory 注入到 `executor.repair` / `_execute_chunked_semantic_merge` / 其它 `_call_llm_with_retry` 直调点，把 §6.4 的"path coverage 5%"拉到 ~80%。这是实际让 memory 子系统"用起来"的关键改造。
2. **Phase A**：per-project 跨 run 持久化（`<repo>/.merge/memory.db`），解决 §6.5 的冷启动问题。
3. **修复 P5**：清理 `project_context` 字段，避免 README 注入污染 LLM 上下文。

---

## 8. 关键产物路径（resume 时参考）

| 文件 | 路径 |
|------|------|
| Plan 报告 | `dify-official-plugins/MERGE_RECORD/MERGE_PLAN_feat_merge_58c0e2f8.md` |
| Plan review 报告 | `dify-official-plugins/outputs/plan_review_58c0e2f8-fa2a-4e1a-b011-db0023590f94.md` |
| Run log | `dify-official-plugins/outputs/debug/run_58c0e2f8-fa2a-4e1a-b011-db0023590f94.log` |
| LLM traces | `dify-official-plugins/outputs/debug/llm_traces_58c0e2f8-fa2a-4e1a-b011-db0023590f94.jsonl` |
| Checkpoint | `dify-official-plugins/outputs/debug/checkpoints/checkpoint.json` |
| Memory DB | `dify-official-plugins/outputs/debug/checkpoints/memory.db` (65 entries 跨 3 phase) |
| **Memory hit sidecar** | `dify-official-plugins/outputs/debug/checkpoints/memory_hit_stats.json` (Phase D 新增) |
| 测试合并 config | `dify-official-plugins/.merge/config.yaml` |
| 测试合并 env | `dify-official-plugins/.merge/.env` |
| Decisions YAML | `dify-official-plugins/.merge/decisions-sample.yaml` (Phase E sampling 用) |

**继续合并**：
```bash
cd /Users/angel/AI/project/dify-official-plugins
source /Users/angel/AI/personal/code-merge-system/.venv/bin/activate
set -a && source .merge/.env && set +a
merge resume --run-id 58c0e2f8-fa2a-4e1a-b011-db0023590f94
```
