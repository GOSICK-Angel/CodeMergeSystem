完整测试记录

  运行基本信息

  - Run ID: 4f76c849-ab64-4e78-bbf4-104205ccd904
  - 目标: test/upstream-13-commits → feat_merge
  - Merge base: 2b506b2bcf52
  - 总时长: ~1.5小时（06:27 → 07:55）

  ---
  Phase 断言记录

  ┌───────────────────────────┬────────────────────┬─────────┬────────────────────────────────────────────────────────────────────────────────────────┐
  │           Phase           │        结果        │  耗时   │                                        关键事件                                        │
  ├───────────────────────────┼────────────────────┼─────────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ INITIALIZE                │ ✅ Pass            │ 0.16s   │ 分类 7439 文件 → 102 个可操作文件（64 auto_safe + 35 auto_risky + 3 human_required）   │
  ├───────────────────────────┼────────────────────┼─────────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ PLANNING                  │ ✅ Pass            │ 0.2s    │ 生成合并计划（auto_safe:64, auto_risky:35, human_required:3），auto_merge_rate=62.7%   │
  ├───────────────────────────┼────────────────────┼─────────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ PLAN_REVIEW               │ ⚠️  LLM_UNAVAILABLE │ 82.7s   │ planner_judge (Anthropic proxy) 502 → 全部 auto_risky 文件升级为人工决策               │
  ├───────────────────────────┼────────────────────┼─────────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ HUMAN_REVIEW（计划级）    │ ✅ Human Decision  │ 0.9s    │ 人工决策：16 个文件全部 confirm_risky/downgrade_safe                                   │
  ├───────────────────────────┼────────────────────┼─────────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ AUTO_MERGE                │ ⚠️  Partial         │ 0.0s    │ 16个用户决策已应用；Layer 依赖链阻止 D-missing 文件；42 个文件路由到 conflict_analysis │
  ├───────────────────────────┼────────────────────┼─────────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ CONFLICT_ANALYSIS         │ ✅ Pass            │ 922s    │ 42 文件（14 rule-based + 28 LLM）；conflict_analyst 用 claude-sonnet-4-6 成功运行      │
  ├───────────────────────────┼────────────────────┼─────────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ HUMAN_REVIEW（文件级）    │ ✅ Human Decision  │ 0.9s    │ 人工决策：24 文件（8 take_current, 12 take_target, 4 semantic_merge）                  │
  ├───────────────────────────┼────────────────────┼─────────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ JUDGE_REVIEW              │ ❌ non-PASS        │ 2303s   │ 2 轮评审；executor circuit breaker 因 proxy 网络错误打开；协商中断                     │
  ├───────────────────────────┼────────────────────┼─────────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ HUMAN_REVIEW（judge决策） │ ✅ Human Accept    │ instant │ 人工决策：judge_resolution: accept，接受 FAIL 裁定以获取完整报告                       │
  ├───────────────────────────┼────────────────────┼─────────┼────────────────────────────────────────────────────────────────────────────────────────┤
  │ GENERATING_REPORT         │ ✅ Complete        │ 1s      │ 报告生成完成                                                                           │
  └───────────────────────────┴────────────────────┴─────────┴────────────────────────────────────────────────────────────────────────────────────────┘

  ---
  人工决策记录

  决策1：计划级审批（Phase: PLAN_REVIEW）
  - 原因：planner_judge LLM 不可用
  - 决策：plan_approval: approve，16 个文件全部 confirm_risky

  决策2：文件级合并策略（Phase: CONFLICT_ANALYSIS）
  - 8个 manifest.yaml → take_current（保留 fork 版本号）
  - 12个 requirements.txt/新增模型文件 → take_target
  - 4个代码文件 → semantic_merge（ReAct.py, function_calling.py, jira.yaml, word_extractor.py）

  决策3：Judge 裁定接受（Phase: JUDGE_REVIEW）
  - 原因：executor circuit breaker 打开，无法修复；接受以完成测试
  - 决策：judge_resolution: accept

  ---
  最终 JudgeVerdict

  裁定: ❌ FAIL（置信度 0.70）

  Critical Issues (56)：
  - 53 个 D-missing 文件未在 HEAD 中：新上游文件（tools/comfyui/、triggers/twilio_trigger/、models/mimo/* 等）因 layer 依赖阻断未被添加
  - 1 个 shadow-path 冲突（YAML 扩展名变体）
  - 1 个 API-breaking 变更（class_service.py 构造函数签名）

  High Issues (3)：
  - tools/jira/provider/jira.yaml：缺少 get_recent_projects 工具（semantic_merge 失败）
  - agent-strategies/cot_agent/strategies/ReAct.py：空类定义存根（SyntaxError）
  - tools/dify_extractor/tools/word_extractor.py：超链接处理 bug

  ---
  优化建议清单

  1. [P0] Proxy 稳定性：cc2.069809.xyz 对 claude-sonnet-4-6 有间歇性 502/网络错误（5-10min 超时），对 claude-opus-4-6 有小概率网络错误。建议：
    - 为 executor 配置更短的 timeout（当前等待 262-295s 才报错）
    - 增加 HTTP 层 keep-alive/retry 设置
    - 考虑使用官方 Anthropic API 端点作为 fallback
  2. [P0] auto_merge Layer 依赖阻止 D-missing 文件：10 层 layer 依赖链导致所有 D-missing 新文件（64 个）无法被 auto_merge 处理。建议：
    - D-missing 文件（新上游文件）不应依赖 layer 依赖，应该直接 git checkout upstream -- <file> 而不通过 executor LLM
    - 增加 --ignore-layer-deps 选项或单独处理 D-missing 文件
  3. [P1] executor circuit breaker 在 judge_review 轮次间重置：3 次失败后 circuit breaker 打开，导致后续所有修复调用被拒绝，judge 无法完成协商。建议：在新的 judge_review round 开始时重置 circuit breaker
  4. [P1] conflict_analyst 的过度 escalate_human：对 confidence=0.3 的所有文件都返回 escalate_human，导致 24/24 文件需要人工决策。建议：提高 conflict_analyst 的规则基础判断能力，特别是对 take_current/take_target 决策的自信度
  5. [P1] semantic_merge 失败处理：executor 失败时 semantic_merge 悄悄 fallback 到 escalate_human，用户不清楚哪些文件的合并内容是空的。建议：在报告中明确标注 semantic_merge 失败的文件，并提供手动合并指引
  7. [P2] Judge 误报 D-missing 文件：Judge 检查工作树发现 D-missing 文件"不在 HEAD"并报 critical 错误，但这些文件本就不在 feat_merge 中（需要合并后才会有）。Judge 应区分"合并前不存在"和"合并后缺失"
  8. [P3] 运行时间优化：本次总耗时 ~1.5小时，主要消耗在 conflict_analysis（922s）和 judge_review（2303s）。建议：对 AUTO_SAFE D-missing 文件跳过 LLM 分析，直接 take_target

  ---
  API 连通性确认（2026-04-20）

  测试端点：cc2.069809.xyz（Anthropic proxy）

  | 模型 | HTTP | 延迟 | 说明 |
  |------|------|------|------|
  | claude-opus-4-6 | ✅ 200 | 2.8s | 真实 Claude，可用 |
  | claude-haiku-4-5-20251001 | ✅ 200 | ~10s | 可用（延迟偏高） |
  | claude-sonnet-4-6 | ❌ 502 | 2.1s | 不可用，需绕过 |

  测试端点：cc2.069809.xyz（OpenAI 兼容接口，OPENAI_BASE_URL）

  | 模型 | HTTP | 延迟 | 说明 |
  |------|------|------|------|
  | gpt-5.4 | ✅ 200 | — | 用户确认可用 |

  ---
  下一步优化清单

  根据本次测试分析，按「影响合并质量」→「系统稳定性」→「效率」排序。

  ## 立即生效（配置级，无需改代码）

  ### [Config-1] 更新 .merge/config.yaml agent 模型分配

  当前 config.yaml 将 planner_judge / conflict_analyst 配置为 claude-sonnet-4-6（502 不可用）。
  按已确认可用模型重新分配：

  ```yaml
  agents:
    planner:
      provider: anthropic
      model: claude-opus-4-6        # 不变，已可用
      api_key_env: ANTHROPIC_API_KEY
    planner_judge:
      provider: openai
      model: gpt-5.4                # 原 gpt-4o → gpt-5.4，走 OPENAI_BASE_URL
      api_key_env: OPENAI_API_KEY
    conflict_analyst:
      provider: anthropic
      model: claude-opus-4-6   
      api_key_env: ANTHROPIC_API_KEY
    executor:
      provider: openai
      model: gpt-5.4                # 原 gpt-4o → gpt-5.4
      temperature: 0.1
      api_key_env: OPENAI_API_KEY
    judge:
      provider: anthropic
      model: claude-opus-4-6       
      temperature: 0.1
      api_key_env: ANTHROPIC_API_KEY
    human_interface:
      provider: anthropic
      model: claude-opus-4-6   
      api_key_env: ANTHROPIC_API_KEY
  ```

  **预期效果**：解除 PLAN_REVIEW 阶段 502 阻断，executor / judge 协商可正常推进。

  ---

  ## P0 代码修复（影响合并完整性）

  ### [Fix-1] D-missing 文件跳过 layer 依赖，直接 checkout
  - **根因**：`auto_merge.py` 中 D-missing 文件参与 layer 依赖计算，依赖链阻塞导致 53/56 critical issues
  - **修复方向**：在 `auto_merge` 阶段识别 `diff_type == "D-missing"` 的文件后，直接执行
    `git checkout <upstream_ref> -- <file>`，不经过 executor LLM，不参与 layer 排序
  - **涉及文件**：`src/core/phases/auto_merge.py`
  - **验收标准**：下次测试 Judge 的 D-missing critical issues 归零

  ### [Fix-2] executor timeout 缩短
  - **根因**：当前 executor 等待 262-295s 才触发超时，circuit breaker 需要 3 次才打开，
    导致 judge_review 阶段在无效等待上消耗 2303s
  - **修复方向**：在 `AgentLLMConfig` 增加 `request_timeout_seconds`（建议默认 60s），
    executor / judge agent 的 HTTP client 传入该值
  - **涉及文件**：`src/models/config.py`、`src/llm/client.py`、`src/agents/executor_agent.py`

  ---

  ## P1 代码修复（影响系统稳定性）

  ### [Fix-3] judge_review 每轮重置 circuit breaker
  - **根因**：`executor_agent.py` circuit breaker 状态跨 judge 协商轮次持续，
    第一轮失败后第二轮所有修复调用被直接拒绝
  - **修复方向**：在 `judge_review.py` 每次进入新 round 循环时，调用
    `executor_agent.reset_circuit_breaker()` 或重新实例化 executor
  - **涉及文件**：`src/core/phases/judge_review.py`、`src/agents/executor_agent.py`

  ### [Fix-4] semantic_merge 失败时显式报告，禁止静默 fallback
  - **根因**：executor 执行 semantic_merge 失败后静默降级为 escalate_human，
    用户不知道文件内容为空（jira.yaml 缺失 get_recent_projects 即此原因）
  - **修复方向**：executor 失败时在 FileDecision 上标记 `merge_failure=True` + `failure_reason`；
    report_writer 对此类文件单独列出，提示需手动合并
  - **涉及文件**：`src/agents/executor_agent.py`、`src/tools/report_writer.py`

  ### [Fix-5] 提高 conflict_analyst 规则覆盖，减少过度 escalate
  - **根因**：confidence=0.3 阈值触发全量 escalate，24/24 文件人工决策
  - **修复方向**：增加规则预判层：
    - manifest.yaml 中仅版本号差异 → 自动 take_current
    - 目标分支纯新增文件（无 current 侧修改）→ 自动 take_target
    - LLM 仅处理规则无法覆盖的真实冲突
  - **涉及文件**：`src/core/phases/conflict_analysis.py`（或对应 agent prompt）

  ---

  ## P2 代码修复（影响报告准确性）

  ### [Fix-6] Judge 排除"合并前即不存在"文件的误报
  - **根因**：Judge 检查工作树时将 D-missing 文件（合并前就不在 current 分支）
    报告为 critical，但这些文件若被 Fix-1 正确处理则不会出现此问题
  - **修复方向**：Judge 在构建 critical issues 列表时，排除已知的 `diff_type == "D-missing"` 文件；
    若 Fix-1 已实施，此问题自动消除
  - **涉及文件**：`src/agents/judge_agent.py`（或 judge prompts）
  - **依赖**：Fix-1 完成后可验证是否仍需此修复

  ---

  ## P3 性能优化

  ### [Opt-1] AUTO_SAFE D-missing 文件跳过 LLM 分析
  - conflict_analysis 阶段对 AUTO_SAFE 的 D-missing 文件直接 take_target，
    不走 LLM，预计可将 conflict_analysis 耗时从 922s 降至 <200s
  - **依赖**：Fix-1 实施后，此项进一步减少 LLM 调用量

  ---

  ## 建议实施顺序

  ```
  Config-1（立即）→ Fix-1（P0，核心完整性）→ Fix-2（P0，超时）
      → Fix-3（P1，稳定性）→ Fix-4（P1，透明度）→ Fix-5（P1，自动化率）
          → Fix-6（P2，视 Fix-1 结果决定）→ Opt-1（P3）
  ```