# code-merge-system 合并流程验证报告

生成时间: 2026-04-29  
被测仓库: `/Users/angel/AI/project/dify-official-plugins`  
测试 worktree: `/Users/angel/AI/project/dify-official-plugins-merge-validation-795016d7-r2`  
code-merge-system: `/Users/angel/AI/personal/code-merge-system`  
run_id: `e410eac5-7ae8-4346-80a9-7d7b2d41217f`

## 1. 测试基线信息

- 远端基准分支: `upstream/main`
- 当前本地基线分支: `cvte-main` 派生出的 `test/cvte-flow-795016d7-r2`
- 选定 upstream commit: `795016d76743a6d65f53e77c42e9eafa662548de`
- commit 标题: `feat: tongyi plugin add glm4.7 model (#2362)`
- 新建测试分支: `test/merge-validation-795016d7`
- merge-base: `2b506b2bcf52c6ef2eac19404c29b7f91e298139`
- 选择理由: 该 commit 位于当前 fork merge-base 之后的短路径上，插件结构完整，并直接触达 `models/tongyi`。本地 `models/tongyi/manifest.yaml` 为 `author: cvte`，而 upstream 该 commit 的 manifest 为 `author: langgenius` 且新增/调整 `glm-4.7` 模型配置，适合验证 cvte 模型托管插件的保护与融合规则。

该 commit 修改文件:

- `models/tongyi/manifest.yaml`
- `models/tongyi/models/llm/_position.yaml`
- `models/tongyi/models/llm/glm-4.7.yaml`

## 2. 插件分类结果

分类规则为 `author` 精确等于 `cvte` 才归为二次开发插件；`cvte-old`、`cvte-test` 等不归为 cvte。

- union 插件数: 285
- base 分支已有插件数: 284
- upstream-only 插件数: 1
- cvte 插件数: 16
- 非 cvte 插件数: 269
- `models/` 下 cvte 模型托管插件数: 6

cvte 插件列表:

- `extensions/oaicompat_cvte_dify_model`
- `models/azure_openai`
- `models/cvte`
- `models/tongyi`
- `models/vertex_ai`
- `models/volcengine_maas`
- `models/xinference`
- `tools/comfyui`
- `tools/dhr`
- `tools/firecrawl`
- `tools/gaode`
- `tools/google_search`
- `tools/hms`
- `tools/image_collage`
- `tools/maxhub`
- `tools/universal`

特殊标记: `models/` 下 `author: cvte` 的模型托管插件:

- `models/azure_openai`
- `models/cvte`
- `models/tongyi`
- `models/vertex_ai`
- `models/volcengine_maas`
- `models/xinference`

完整分类列表已写入 `doc/test-report/plugin-classification.csv`。其中 `models/siliconflow` 是本次 upstream-only 新增/引入的非 cvte 插件。

## 3. 合并过程分析

执行方式:

```bash
merge validate --config .merge/config.yaml
merge test/merge-validation-795016d7 --ci --auto-decisions .merge/auto-decisions-795016d7.yaml
merge resume --checkpoint .merge/runs/e410eac5-7ae8-4346-80a9-7d7b2d41217f/checkpoint.json --decisions .merge/judge-accept-795016d7.yaml
```

阶段结果:

- `analysis`: completed
- `plan_review`: completed，PlannerJudge 第 0 轮要求将 `tools/jira/tools/auth.py` 从 `auto_safe` 提升为 `auto_risky`，第 1 轮 approved
- `auto_merge`: completed
- `conflict_analysis`: completed
- `judge_review`: completed，最终 verdict 为 `fail`
- `report`: completed。这里的 completed 表示报告生成完成，不表示合并质量通过

计划统计:

- file_diffs: 133
- plan files: 122
- auto_safe: 112
- auto_risky: 10
- human_required: 0
- file_decision_records: 127
- 决策分布: `take_target` 114，`semantic_merge` 8，`escalate_human` 5

人工/自动决策要点:

- `models/tongyi` 按 cvte 模型托管插件处理，保留本地 `author: cvte` 与本地 manifest 版本，同时融合 `_position.yaml` 中的 `glm-4.7` 模型项。
- `models/siliconflow/requirements.txt` 与 `models/siliconflow/models/llm/_position.yaml` 为非 cvte upstream-only 插件，按规则选择 `take_target`。
- judge 第 0 轮 fail 发现 7 个问题，系统修复/重审后第 1 轮仍 fail，剩余 1 个 critical 与 1 个 info。
- 为生成终态报告，最后明确设置 `judge_resolution: accept`；这表示接受 FAIL 结论并进入报告阶段，不代表测试通过。

## 4. 冲突处理详情

详表见 `doc/test-report/conflict-files.csv`。关键结论如下:

- PASS: `models/tongyi/manifest.yaml` 保留本地 cvte 托管身份，避免 upstream 覆盖为 `langgenius`。
- PASS: `models/tongyi/models/llm/_position.yaml` 融合了 upstream `glm-4.7`，未破坏本地模型托管 manifest。
- PASS: `extensions/openai_compatible/manifest.yaml`、`models/deepseek/manifest.yaml`、`models/openai_api_compatible/manifest.yaml` 等非 cvte version conflict 采用 upstream。
- FAIL: `models/siliconflow/manifest.yaml` 留下未跟踪文件且包含冲突标记，未进入 pending_user_decisions；最终 YAML 解析失败。
- FAIL: judge 判定 `agent-strategies/cot_agent/strategies/function_calling.py` 是 B-class mismatch，合并后与 upstream 不一致。

## 5. 流程验证结论

| 验证点 | 结果 | 说明 |
| --- | --- | --- |
| 插件识别是否正确 | PASS | union 共 285 个插件，完整 CSV 已生成 |
| author 分类是否正确 | PASS | 使用 `author == cvte` 精确判断，`cvte-old`/`cvte-test` 未误判 |
| cvte models 特殊标记 | PASS | 识别 6 个模型托管插件 |
| 冲突识别是否完整 | FAIL | `models/siliconflow/manifest.yaml` 含冲突标记但未进入 pending decisions |
| 合并策略是否符合规则 | PARTIAL | tongyi/cvte 策略正确，多个非 cvte 采用 upstream；但 siliconflow manifest 与 B-class 文件失败 |
| 最终结果是否可用 | FAIL | 工作树仍有 YAML parse error 与冲突标记，judge verdict 为 fail |

总体结论: **FAIL**。这次是新的 commit 完整流程验证，系统能跑到报告阶段，但合并结果不满足“最终可用、结构完整”的要求。

## 6. Memory 系统利用率与优化空间

首轮干净流程在 resume conflict_analysis 时暴露 blocker:

- 错误: `SQLiteMemoryStore.get_relevant_context() got an unexpected keyword argument min_relevance`
- 修复: `src/memory/sqlite_store.py` 增加 `min_relevance` 参数并按阈值过滤；补充 `tests/unit/test_sqlite_memory_store.py::test_filters_by_min_relevance`
- 验证: `pytest tests/unit/test_sqlite_memory_store.py tests/unit/test_layered_loader.py -q` 通过 50 项；`ruff check` 与 `mypy src/memory/sqlite_store.py` 通过

最终 run 的 memory 利用率:

- Memory 加载次数: 28
- 命中次数: 28
- 命中率: 100%
- auto_merge: 3 次调用，3 次命中
- conflict_analysis: 5 次调用，5 次命中
- judge_review: 20 次调用，20 次命中
- 报告汇总 L1 previous decisions: 71，L2 file entries: 33，L0 project profile: 0

可优化点:

- 将插件 author 分类与 cvte model-hosting 标记写入 L0 project profile，避免各阶段重复推断。
- 对 judge_review 的 20 次上下文加载做 batch/file 缓存；当前命中率高，但调用次数偏多。
- 将 conflict-marker 扫描结果写入 memory，并强制进入 pending decisions，避免 `models/siliconflow/manifest.yaml` 这种未跟踪冲突文件漏检。
- judge_review 长时间无 checkpoint 心跳，建议给外部模型调用增加阶段级 timeout/heartbeat 与可恢复状态。

## 7. 存在的问题与改进建议

1. **冲突标记漏检**: `models/siliconflow/manifest.yaml` 是未跟踪文件，含 `<<<<<<<`，但未进入 pending decisions，最终仍被 report 阶段放过。建议在 auto_merge、conflict_analysis、judge_review、report 前统一扫描 tracked + untracked 文件。
2. **结构完整性 gate 不足**: 当前最终状态可以 completed，但 manifest YAML 已不可解析。建议 report 前增加插件结构 gate: 所有 `manifest.yaml` 必须可解析，且不能含冲突标记。
3. **非 cvte upstream 策略存在残留失败**: judge 发现 `agent-strategies/cot_agent/strategies/function_calling.py` 与 upstream 不一致。建议对非 cvte/B-class 文件加入 blob equality gate，失败时自动切回 target 或阻断完成。
4. **决策计数不直观**: CLI 输出曾出现 `total_files: 122` 但 `auto_merged: 127`，容易误导。建议区分 plan files、decision records、repair records。
5. **memory API 契约缺测试**: `min_relevance` 调用方与 SQLiteMemoryStore 实现不一致，已修复；建议为 MemoryStore 与 SQLiteMemoryStore 建共享契约测试。

## 8. 产物路径

- 流程报告: `/Users/angel/AI/personal/code-merge-system/doc/test-report/merge-validation-report.md`
- 插件分类 CSV: `/Users/angel/AI/personal/code-merge-system/doc/test-report/plugin-classification.csv`
- 冲突文件 CSV: `/Users/angel/AI/personal/code-merge-system/doc/test-report/conflict-files.csv`
- code-merge-system 原始 merge report: `/Users/angel/AI/project/dify-official-plugins-merge-validation-795016d7-r2/.merge/runs/e410eac5-7ae8-4346-80a9-7d7b2d41217f/merge_report_e410eac5-7ae8-4346-80a9-7d7b2d41217f.md`
- checkpoint: `/Users/angel/AI/project/dify-official-plugins-merge-validation-795016d7-r2/.merge/runs/e410eac5-7ae8-4346-80a9-7d7b2d41217f/checkpoint.json`
