## 对比表

| 项目                     | 更像你系统里的哪一层             | 能借鉴的点                                                                                                                                                                | 关键不足                                                                                                                   | 适合作为你的基座吗                                                           |
| ---------------------- | ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| **weave**              | **底层语义合并引擎**           | 用 tree-sitter 做 **entity-level semantic merge**，按函数 / 类 / JSON key 这类语义实体做三方合并，不只是按行；仓库还给出了 `weave-core / weave-driver / weave-cli` 这种比较清晰的分层。([GitHub][1])          | 它强在“怎么更聪明地 merge”，但不是你要的完整 **multi-agent merge workflow**；没有你想要的 Planner / Judge / Human Decision 文档这一整套。([GitHub][1]) | **很适合做底座之一**。如果你自己做系统，我会优先把它当成“合并内核”候选。([GitHub][1])                |
| **Mergiraf**           | **结构化 merge driver**   | 明确是 **syntax-aware git merge driver**，而且强调“遇到可疑情况宁可保留 conflict markers，也不要过度乐观地自动吞冲突”，这点和你“不能 silent resolve”非常一致。还支持 `review` 工作流。([Mergiraf][2])                   | 更偏“语法感知合并工具”，不是基于冲突**原因追溯**和多角色协作来决策；也不提供 judge / hitl 编排。([Mergiraf][2])                                              | **适合做 merge engine 参考**，但不够当你完整系统的骨架。([Mergiraf][2])                |
| **rizzler**            | **LLM 冲突解决器**          | 可以直接作为 Git merge driver 接进流程，核心思路就是“发生冲突时调用 LLM 处理”，实现路径很贴近你未来可能接 Codex/Claude/OpenAI 的方式。([GitHub][3])                                                              | 更像“AI 帮你解冲突”的单点工具，不是可审计的多 agent 系统；也缺你强调的**独立审查、决策升级、原因追溯**。([GitHub][3])                                              | **可参考接入方式，不适合直接做基座**。([GitHub][3])                                  |
| **Git With Intent**    | **接近“AI 编排 + 审批门禁”层**  | README 直接写了 **semantic merge conflict resolution**、`autopilot`、`approval gating`，这和你想要的“自动执行但关键点要人批准”很接近。([GitHub][4])                                               | 它更偏 **PR 自动化 CLI**，不是专门面向“长期分叉仓库历史追溯式合并”；而且仓库标的是 **BSL 1.1**，更接近源码可见，不太适合当纯开源基座来深度复用。([GitHub][4])                     | **值得重点研究产品形态**，但不一定适合直接 fork 当底座。([GitHub][4])                      |
| **vit**                | **hitl + 验证增强的语义合并流程** | 它的流程很值得借鉴：**先尝试 git merge → 再做 post-merge validation → 有问题再送 LLM → 用户确认后写回**。而且明确支持 **interactive conflict clarification** 和 **post-merge validation**。([GitHub][5]) | 这是 **视频编辑领域** 的专用 git，不是通用代码仓库 merge 系统；它解决的是“跨 domain 文件的一致性”，不是大规模通用代码分叉合并。([GitHub][5])                             | **很适合借鉴 human-in-the-loop 流程设计**，但不适合直接拿来做代码 merge 基座。([GitHub][5]) |
| **Agent Orchestrator** | **多 agent 调度与执行编排层**   | 它明确支持 **parallel AI coding agents**、每个 agent 自己的 **git worktree / branch / PR**，还能自动处理 **CI failures、merge conflicts、code reviews**。这很像你系统未来的“任务编排总控”。([GitHub][6])  | 它关注的是“并行 coding agents 的 orchestration”，不是“长期分叉 merge 的语义分析与裁决系统”；合并只是它覆盖的一部分。([GitHub][6])                            | **适合借鉴调度层，不适合充当 merge 核心**。([GitHub][6])                            |
| **MetaGPT**            | **角色分工范式**             | 它最值得借鉴的是 **PM / Architect / Engineer** 这种多角色 SOP 协作方式，非常适合映射到你设想的 **Planner / Executor / Judge / Conflict Analyst**。([GitHub][7])                                    | 它不是 Git merge 产品；更偏通用多 agent 软件生产框架。直接拿来做 merge system，会缺很多 git / diff / blame / review 细节。([GitHub][7])               | **适合借鉴角色设计，不适合直接当 merge 底座**。([GitHub][7])                          |
| **git-regress**        | **Judge / 审查门禁增强层**    | 它做的事很对你胃口：专门检测 **git 冲突检测发现不了的 semantic regressions**，例如 PR A 新增的 symbol 被 PR B 的后续重构静默删除。它用 tree-sitter 提取 symbol footprint，再和后续 PR 删除/修改做交叉比对。([GitHub][8])        | 它不做 merge，只做“合并后 / PR 阶段的语义回归告警”；当前 README 里也明确 v1 只支持 JS/TS。([GitHub][8])                                             | **非常适合并入你的 Judge 层**，但不是主系统基座。([GitHub][8])                         |

## 我的结论

**最像你想做的“完整系统”的，没有看到完全同类。**
GitHub 上更像是每个项目只覆盖一段能力：

* **weave / Mergiraf**：解决“怎么更聪明地 merge”([GitHub][1])
* **rizzler / Git With Intent**：解决“怎么让 AI 介入冲突处理或 PR 自动化”([GitHub][3])
* **Agent Orchestrator / MetaGPT**：解决“怎么做多 agent 分工与编排”([GitHub][6])
* **git-regress**：解决“怎么发现静默语义回归”([GitHub][8])

而你要的是把这些能力**组合成一个面向长期分叉合并的完整产品**：
**规划 → 文件分类 → 语义冲突分析 → 原因追溯 → 自动/半自动决策 → 独立 Judge 审查 → Human-in-the-loop 裁决 → 最终门禁**。这一整套我目前没搜到成熟开源项目直接覆盖。([GitHub][1])

## 我建议你优先研究的顺序

**如果目标是自己做一个可落地 MVP：**

**第一梯队：必须看**

1. **weave**：看它怎么做 entity-level 3-way merge，最接近你的“语义融合内核”。([GitHub][1])
2. **git-regress**：看它怎么做 symbol footprint / semantic regression 检测，很适合塞进你的 Judge。([GitHub][8])
3. **Agent Orchestrator**：看它怎么调度多 agent、隔离 worktree、衔接 CI / PR。([GitHub][6])

**第二梯队：重点借鉴产品流程**
4. **Git With Intent**：看 approval gating、autopilot、语义 merge 交互。([GitHub][4])
5. **vit**：看 post-merge validation + user confirmation 的 hitl 流程。([GitHub][5])

**第三梯队：可选参考**
6. **Mergiraf**：看“保守而不 silent resolve”的 merge driver 策略。([Mergiraf][2])
7. **MetaGPT**：看角色化 SOP，不是 merge 专项。([GitHub][7])
8. **rizzler**：看最直接的 LLM merge driver 接法。([GitHub][3])

## 最实际的路线

如果让我给你一个**最现实的架构拼装方案**，我会建议：

* **合并内核**：参考 `weave` / `Mergiraf` 的结构化 merge 思路([GitHub][1])
* **多 agent 调度**：参考 `Agent Orchestrator` / `MetaGPT` 的角色协作和任务编排([GitHub][6])
* **审查门禁**：吸收 `git-regress` 的 symbol-level regression 检测([GitHub][8])
* **人工裁决流**：借鉴 `vit` 和 `Git With Intent` 的 user confirmation / approval gating([GitHub][9])

这样拼出来的东西，会比单独 fork 任意一个项目更接近你的目标。

我可以下一步直接帮你输出一版：**“基于这些开源项目的系统架构蓝图”**，把每个项目该借哪一层、替代哪一层，画成一张更清晰的设计图。

[1]: https://github.com/ataraxy-labs/weave?utm_source=chatgpt.com "Ataraxy-Labs/weave: Entity-level semantic merge driver ..."
[2]: https://mergiraf.org/?utm_source=chatgpt.com "Mergiraf: Introduction"
[3]: https://github.com/ghuntley/rizzler?utm_source=chatgpt.com "rizzler: stop crying over Git merge conflicts and let AI ..."
[4]: https://github.com/intent-solutions-io/iam-git-with-intent?utm_source=chatgpt.com "intent-solutions-io/iam-git-with-intent"
[5]: https://github.com/LucasHJin/vit?utm_source=chatgpt.com "LucasHJin/vit: Git for video editing."
[6]: https://github.com/ComposioHQ/agent-orchestrator?utm_source=chatgpt.com "Agentic orchestrator for parallel coding ..."
[7]: https://github.com/FoundationAgents/MetaGPT?utm_source=chatgpt.com "FoundationAgents/MetaGPT: 🌟 The Multi-Agent ..."
[8]: https://github.com/TonyStef/git-regress/blob/main/README.md?utm_source=chatgpt.com "git-regress/README.md at main"
[9]: https://github.com/LucasHJin/vit/blob/main/CLAUDE.md?utm_source=chatgpt.com "vit/CLAUDE.md at main · LucasHJin/vit"
