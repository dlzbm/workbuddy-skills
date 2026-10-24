---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
agent_created: true
---

---

## WorkBuddy 适配说明

移植自 [mattpocock/skills](https://github.com/mattpocock/skills) 的 engineering 分类（MIT）。
原文方法内容未改，仅以下三点适配：

1. **子代理映射**：WorkBuddy 的 Agent 工具支持 `subagent_type` 为 `Explore`（只读代码探索，对应 exploration subagent）与 `general-purpose`（多步执行，对应 implementer subagent）。文中出现的 subagent / exploration subagent / implementer subagent 一律按此映射，其余约定（context pointer、稀疏通信、并行 frontier）照原文执行。
2. **仅用户显式调用**：上游对该技能标记了 `disable-model-invocation`（Codex 侧为 `policy.allow_implicit_invocation = false`），即只在用户明确点名时执行，不要模型自己触发。
3. **Issue tracker**：多个技能假设存在 issue tracker（Linear 等）。没有 tracker 时，把 ticket / spec / 决策记录落到仓库内 `docs/` 下的 Markdown 文件即可，流程不变。

Implement the work described by the user in the spec or tickets.

If the user passes a ticket reference, fetch it from the issue tracker and state its title before starting. If the reference is ambiguous, ask.

Call the Skill tool with "tdd" where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, call the Skill tool with "code-review" to review the work.

Commit your work to the current branch.
