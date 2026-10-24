---
name: research
description: Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.
agent_created: true
---

---

## WorkBuddy 适配说明

移植自 [mattpocock/skills](https://github.com/mattpocock/skills) 的 engineering 分类（MIT）。
原文方法内容未改，仅以下三点适配：

1. **子代理映射**：WorkBuddy 的 Agent 工具支持 `subagent_type` 为 `Explore`（只读代码探索，对应 exploration subagent）与 `general-purpose`（多步执行，对应 implementer subagent）。文中出现的 subagent / exploration subagent / implementer subagent 一律按此映射，其余约定（context pointer、稀疏通信、并行 frontier）照原文执行。
2. **可被模型触发**：上游未限制触发方式，模型可按 description 主动选用。
3. **Issue tracker**：多个技能假设存在 issue tracker（Linear 等）。没有 tracker 时，把 ticket / spec / 决策记录落到仓库内 `docs/` 下的 Markdown 文件即可，流程不变。

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not a secondary write-up of them. Follow every claim back to the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source.
3. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.
