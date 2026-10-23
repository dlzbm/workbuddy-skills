---
name: webnovel-writer
description: 长篇中文网文创作插件（WorkBuddy 移植版）。该技能按单条命令执行具体动作——新建项目、规划某一卷、写某一章、审查某章、查询设定伏笔、润色去AI味，内置 Story System 一致性合同树、五维事实审查、7层Anti-AI去模板腔规范、9个题材写法数据表。当用户要精细控制单一步骤时使用（如「写第18章」「规划第2卷」「审查第30章」「查一下这个伏笔」「这章AI味太重」）。需要连续自动写完整卷或批量推进多章时，改用 webnovel-autopilot。触发词：写第N章、规划第N卷、审查第N章、查询设定、去AI味、建设定集、webnovel。
agent_created: true
---

# Webnovel Writer（WorkBuddy 移植版）

移植自 `webnovel-writer 6.2.1`（GPL-3.0）。用户现有三本书《逐我出宗》《身上符咒》《全网围观》均由本插件生成，现有项目的 `.webnovel/` `.story-system/` 目录结构与之完全兼容。

## 每次调用的第一步（必须）

WorkBuddy 每次 Bash 调用是独立 shell，环境变量不持久。**每次执行命令前先重设这三项**：

```bash
export WNW="$HOME/.workbuddy/skills/webnovel-writer"
export BOOK="<书目录绝对路径>"

"$WNW/wnw" --project-root "$BOOK" preflight
```

- `wnw` 是 `scripts/webnovel.py` 的包装器，已内置隔离 Python 与 `PYTHONPATH`，不要绕过它直接调 `python`。
- `preflight` 必须全部 `OK`。出现 `BLOCKER` 就停下来报用户，**不要自己写替代逻辑**。
- Python 依赖（aiohttp / filelock / pydantic）装隔离环境即可；`wnw` / `refs` 会自动按平台探测
  `~/.workbuddy/binaries/python/envs/webnovel`（macOS/Linux 用 `bin/python`，Windows 用 `Scripts/python.exe`），
  探测不到就回退系统 `python3`。想强制指定：`export WNW_PYTHON="/绝对路径/bin/python"`。

### 顺便记住

| 命令 | 用途 |
|---|---|
| `"$WNW/wnw" --project-root "$BOOK" where` | 输出项目根路径 |
| `"$WNW/wnw" --project-root "$BOOK" run-ledger write-resume --chapter N --mode default --format json` | 查本章断点续跑位置 |

## 命令路由

按用户意图读对应命令文档，**读完再动手**，不要凭印象执行：

| 用户意图 | 读这份文档 |
|---|---|
| 新建书 / 建设定集 / 写总纲 | `skills/webnovel-init/SKILL.md` |
| 规划某一卷 / 拆章纲 | `skills/webnovel-plan/SKILL.md` |
| **写章 / 续写下一章**（最常用） | `skills/webnovel-write/SKILL.md` |
| 单独审查某章 | `skills/webnovel-review/SKILL.md` |
| 查询设定 / 角色 / 伏笔 / 进度 | `skills/webnovel-query/SKILL.md` |
| 把有效写法沉淀进项目记忆 | `skills/webnovel-learn/SKILL.md` |
| 排查环境问题 | `skills/webnovel-doctor/SKILL.md` |
| **无人值守连写整卷 / 批量推进** | `skills/webnovel-autopilot/SKILL.md` |

本书上下文相关的通用参考：`references/README.md`（导航）、`references/shared/`。

---

## 关键适配：主流程代劳模式

> 这是本移植版与原插件唯一的实质性差异，务必理解后再执行写章。

原插件的写章流程 Step 1 / Step 3 / Step 5 要求用 Claude Code 的 `Agent` 工具调用三个自定义子代理。**WorkBuddy 的 Agent 工具不支持插件自定义子代理类型**，因此统一改为代劳模式：

**由主流程直接读取角色文档，按其职责、输入契约、输出 schema 完成同等质量的工作，并产出完全相同的 artifact 文件。**

| 原 Subagent | 必读角色文档 | 代劳必须产出 |
|---|---|---|
| context-agent | `agents/context-agent.md` | 五段式写作任务书（写入 factor） |
| reviewer | `agents/reviewer.md` | `.webnovel/tmp/review_results.json` |
| data-agent | `agents/data-agent.md` | `fulfillment_result.json` / `disambiguation_result.json` / `extraction_result.json` |

代劳时的三条硬要求：

1. **先读角色文档再动手**，不要凭印象生成 JSON。三份文档的 schema 各不相同。
2. **schema 必须完整**。最容易踩的坑是 reviewer 的 `dimension_results`——必须覆盖 `setting` / `timeline` / `continuity` / `character` / `logic` 五个维度，无问题也要显式写 `"conclusion": "pass"`。缺失会导致下游 `review-pipeline` 与 `write-gate` 判定异常。
3. **reviewer 只产出如上三份 JSON**，由主流程用 Write 工具落盘；role boundary 不得混淆（例如 reviewer 不持 Write）。

除上述三点外，写章流程的**每一步、每一个 gate、每一份 artifact 都照原样执行**，不允许因为是代劳就跳过 `write-gate` 或 `chapter-commit`。

---

## 写章流程要点（配合 `skills/webnovel-write/SKILL.md` 使用）

完整六步见原文档。这里只强调最容易出错的地方：

### Step 2 起草前

- 写作任务书必须先在 Step 1 产出，**禁止主流程自己拼一个简版任务书**。
- 传给 `story-system` 的 query 必须是**真实的本章目标**，禁止传 `{章纲目标}`、`第N章章纲目标` 这类占位符。
- 任务书五段顺序固定：硬性约束 → CBN/CPNs/CEN → 本章禁区 → 风格指引 → dynamic_context 补充。

### Step 4 润色：这是决定「文风」的一步

`references/polish-guide.md` 有 16KB，**不要全文读**。按区段读：

```bash
grep -n "^#\{1,3\} " "$WNW/skills/webnovel-write/references/polish-guide.md"
```

主路径取 `## 2. 执行顺序（必须按序）`；Anti-AI 词库取 `## 2A. Anti-AI 检测细则` 与 `## Phase 1 增补：Anti-AI 规范（7层，原版）`。

执行顺序不可乱：修复审查问题 → 网文化 Hard/Soft/Style 校验 → Anti-AI 终检 → No-Poison 毒点检查 → 输出 `anti_ai_force_check: pass/fail`。

**7 层 Anti-AI 规范必须全文逐段检查，不得抽样**。命中项要么改写，要么记入 deviation。检查结果为 `fail` 时**不得进入 Step 5**。

短文件可全文读：`skills/webnovel-write/references/writing/typesetting.md`、`references/style-adapter.md`。

### Step 3 / Step 5 的 artifact

- 三份 artifact 必须以**完全相同的文件名**落到 `.webnovel/tmp/`，否则 `chapter-commit` 会因缺输入而失败。
- `review-pipeline` 会把 `review_results.json` 覆盖为标准 artifact（含 `blocking_count`），供 precommit gate 使用。Step 3 之后必须跑它。

---

## CSV 写法数据表（Step 2 按需调用）

9 张结构化数据表存放在 `references/csv/`，用 BM25 字面召回：

```bash
"$WNW/refs" --skill write --table 桥段套路 --query "当众揭露证据" --max-results 3
```

可用表名：`人设与关系` `写作技法` `命名规则` `场景写法` `桥段套路` `爽点与节奏` `裁决规则` `金手指与设定` `题材与调性推理`。

**重要**：`--genre` 过滤会大幅收窄结果（很多条目的 `适用题材` 标注较窄）。**默认不要传 `--genre`**，只有在明确要限定题材时才用；无题材过滤也搜不到时，换关键词而不是放弃。

触发场景：新角色→`命名规则`，战斗→`场景写法`，多角色对话→`写作技法`，情感描写→`写作技法`，高频桥段→`桥段套路`。

---

## 硬规则

- 禁止并步、跳步、伪造审查、伪造 commit。
- 失败只补跑失败步骤，不回退已完成的步骤。
- **大纲即法律**：正文不得偏离卷细纲；想改剧情先改大纲。
- **设定即物理**：能力/境界/已发生事实不可回退；写错了改正文，不改设定。
- 审查只跑一轮，reviewer 只调用一次。blocking issue 定点修复后直接进下一步，不重复审查。
- 少打扰：默认继续推进，只在创作方向、事实一致性、文件覆盖风险或 blocking 无法定点处理时才问用户，且给 2-3 个有限选项。
- 最终回复面向作者，**不输出原始 JSON、traceback 或长命令日志**。用固定三段式（成果 / 问题 / 下一步）。

## 已知环境限制（记录一次，不要每次重复排查）

- **未配置 `EMBED_API_KEY`（本机现状：无可用 ModelScope token）已改造为「预期降级」，不再是故障。** 结论长期有效，不要每次重新排查：
  - `projection_status.vector` 落 `skipped`，**不会**再让 `doctor` 报 `projection_failed`、`write-gate` 报 `phase_not_ready_*`。编排层按正常流程调用 gate 即可，无需跳过。
  - 提交章节时跳过远端向量化，但仍把 summary / 事件 / 场景 / 实体增量写入本地 `.webnovel/vectors.db` 并建立 BM25 关键词索引，**跨章检索依旧可用**，全程不联网。
  - BM25 采用「中文单字 + 相邻二元组」分词（无 jieba 依赖）。召回够用，但语义联想弱于向量：同义改写、跨章伏笔的间接呼应可能捞不到，别指望它替代 `previous_summaries` 和 Story System 合同。
  - `RERANK_API_KEY` 同样缺失 → 无 rerank 精排，结果直接用 BM25 原始分。
  - 设 `WEBNOVEL_DISABLE_VECTOR=1`（或 `true`/`yes`/`on`）可强制走纯 BM25，即使已配 key 也不请求远端。
- **历史章节补语料**：从未成功写过向量的旧章节，需要先补一次 `projections replay --from-chapter 1 --to-chapter N` 才能有跨章召回素材。该命令幂等、可重复执行。将来配好 key 后同样再跑一次 replay 即可把真向量补上。
- 本书项目各自维护 git 仓库，`backup` 必须以解析后的 `PROJECT_ROOT` 为准，禁止在工作区父目录执行裸全量 `git add`。
