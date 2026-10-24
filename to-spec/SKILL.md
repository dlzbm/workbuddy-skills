---
name: to-spec
description: "Turn the current conversation into a spec and publish it to the project issue tracker: no interview, just synthesis of what you've already discussed."
agent_created: true
---

---

## WorkBuddy 适配说明

移植自 [mattpocock/skills](https://github.com/mattpocock/skills) 的 engineering 分类（MIT）。
原文方法内容未改，仅以下三点适配：

1. **子代理映射**：WorkBuddy 的 Agent 工具支持 `subagent_type` 为 `Explore`（只读代码探索，对应 exploration subagent）与 `general-purpose`（多步执行，对应 implementer subagent）。文中出现的 subagent / exploration subagent / implementer subagent 一律按此映射，其余约定（context pointer、稀疏通信、并行 frontier）照原文执行。
2. **仅用户显式调用**：上游对该技能标记了 `disable-model-invocation`（Codex 侧为 `policy.allow_implicit_invocation = false`），即只在用户明确点名时执行，不要模型自己触发。
3. **Issue tracker**：多个技能假设存在 issue tracker（Linear 等）。没有 tracker 时，把 ticket / spec / 决策记录落到仓库内 `docs/` 下的 Markdown 文件即可，流程不变。

This skill takes the current conversation context and codebase understanding and produces a spec. Do NOT interview the user; just synthesize what you already know.

The issue tracker and triage label vocabulary should have been provided to you. If not, tell the user to run `/setup-matt-pocock-skills`.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the spec, and respect any ADRs in the area you're touching.

2. Sketch out the seams at which you're going to test the feature. Existing seams should be preferred to new ones. Use the highest seam possible. If new seams are needed, propose them at the highest point you can. The fewer seams across the codebase, the better - the ideal number is one.

Check with the user that these seams match their expectations.

3. Write the spec using the template below, then publish it to the project issue tracker. Apply the `ready-for-agent` triage label - no need for additional triage.

<spec-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A LONG, numbered list of user stories. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

This list of user stories should be extremely extensive and cover all aspects of the feature.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Out of Scope

A description of the things that are out of scope for this spec.

## Further Notes

Any further notes about the feature.

</spec-template>
