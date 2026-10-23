# webnovel-writer（WorkBuddy 移植版）

长篇中文网文创作技能包。由原本分开的 **`webnovel-writer`（执行层）** 与 **`webnovel-autopilot`（编排层）** 合并而成，一个包覆盖「单步精修」到「无人值守连写整卷」两种用法。

> 移植自 `webnovel-writer 6.2.1`（GPL-3.0），协议见本目录 [LICENSE](./LICENSE)。
> 上层仓库：[dlzbm/workbuddy-skills](https://github.com/dlzbm/workbuddy-skills)

---

## 两层职责

| 层 | 入口 | 干什么 | 什么时候用 |
|---|---|---|---|
| **执行层** `webnovel-writer` | 根 `SKILL.md` + `skills/webnovel-*/` | 按单条命令执行一个具体动作：建书、规划卷、写章、审查、查设定、润色 | 要精细控制单一步骤：「写第 18 章」「规划第 2 卷」「审查第 30 章」「这章 AI 味太重」 |
| **编排层** `webnovel-autopilot` | `skills/webnovel-autopilot/SKILL.md` | 探测断点 → 循环调度 init/plan/write → 停在干净断点 | 要连续推进：「自动写完这一卷」「批量写 5 章」「继续写」「一句话创意写成一本书」 |

两层共用同一套底层流程与同一批产物，编排层不重写任何内部逻辑。

## 能力一览

| 命令 | 用途 |
|---|---|
| `/webnovel-init` | 深度初始化：项目骨架、设定集、总纲（含反套路与卖点设计） |
| `/webnovel-plan` | 卷纲、时间线、章纲拆解，并把新增设定增量写回设定集 |
| `/webnovel-write` | 一条龙写章：上下文 → 起草 → 审查 → 润色 → 提交 → 备份 |
| `/webnovel-review` | 多维度审查章节并把指标落库 |
| `/webnovel-query` | 查询设定、角色、伏笔、金手指状态、进度（只读） |
| `/webnovel-learn` | 把本轮有效写法沉淀进项目长期记忆 |
| `/webnovel-dashboard` | 启动只读可视化面板 |
| `/webnovel-doctor` | 只读体检：环境、目录、JSON、SQLite、RAG 配置 |
| `/webnovel-autopilot` | 自动连写编排（合并进本包） |

## 安装

```powershell
# Windows PowerShell
robocopy "<仓库路径>\webnovel-writer" "$env:USERPROFILE\.workbuddy\skills\webnovel-writer" /E
```

```bash
# macOS / Linux
cp -r webnovel-writer ~/.workbuddy/skills/
```

Python 依赖（`aiohttp` / `filelock` / `pydantic`）：

```bash
python -m venv ~/.workbuddy/binaries/python/envs/webnovel
~/.workbuddy/binaries/python/envs/webnovel/bin/python -m pip install -r scripts/requirements.txt
```

`wnw` / `refs` 两个入口脚本会自动按平台探测该虚拟环境（Linux/macOS 找 `bin/python`，Windows 找 `Scripts/python.exe`），探测不到就回退系统 `python3`；也可 `export WNW_PYTHON="/绝对路径/bin/python"` 显式指定。

## 快速开始

WorkBuddy 每次 Bash 调用是独立 shell，**每条命令前都要重设这两个变量**：

```bash
export WNW="$HOME/.workbuddy/skills/webnovel-writer"
export BOOK="<书目录绝对路径>"

"$WNW/wnw" --project-root "$BOOK" preflight     # 必须全 OK；出现 BLOCKER 就停下报用户
```

写一章：

```bash
"$WNW/wnw" --project-root "$BOOK" write --chapter 18
```

查写法数据表（9 张结构化 CSV，BM25 字面召回）：

```bash
"$WNW/refs" --skill write --table 桥段套路 --query "当众揭露证据" --max-results 3
# 表名：人设与关系 写作技法 命名规则 场景写法 桥段套路 爽点与节奏 裁决规则 金手指与设定 题材与调性推理
# 注意：默认不要传 --genre，会大幅收窄结果
```

无人值守连写：直接说「自动写完这一卷」或「继续写」，由 autopilot 接管。

## 关键机制

| 机制 | 说明 |
|---|---|
| **Story System 一致性合同树** | 每章的 `chapter_directive` / `forbidden_zones` 由合同驱动，写章前必须就位 |
| **五维事实审查** | `setting` / `timeline` / `continuity` / `character` / `logic`，无问题也要显式 `pass` |
| **7 层 Anti-AI 去模板腔** | 逐段全文检查（禁止抽样），`fail` 不得进入提交步骤 |
| **9 张写法 CSV** | 桥段、爽点、场景、命名、金手指等结构化数据，起草时按需召回 |
| **章节提交与备份** | `chapter-commit` 返回 `accepted`/`rejected` 才是唯一准绳，随后自动 `backup` |

### WorkBuddy 移植差异：主流程代劳模式

原插件依赖 Claude Code 的自定义子代理（context-agent / reviewer / data-agent），WorkBuddy 的 Agent 工具不支持。**改为由主流程读取 `agents/*.md` 角色文档后代劳**，产出完全相同的 artifact 文件：

| 原 Subagent | 必读文档 | 代劳必须产出 |
|---|---|---|
| context-agent | `agents/context-agent.md` | 五段式写作任务书 |
| reviewer | `agents/reviewer.md` | `.webnovel/tmp/review_results.json` |
| data-agent | `agents/data-agent.md` | `fulfillment_result.json` / `disambiguation_result.json` / `extraction_result.json` |

三条硬要求：先读角色文档再动手（三份 schema 各不相同）；schema 必须完整（尤其 `dimension_results` 五维）；三份 artifact 必须落盘到 `.webnovel/tmp/`，文件名不得改。

除这三点外，每一步 gate、每一份 artifact 都照原样执行，不允许因为是代劳就跳过 `write-gate` 或 `chapter-commit`。

## 目录结构

```
webnovel-writer/
├── SKILL.md                      执行层入口（命令路由 + 代劳模式 + 硬规则）
├── README.md                     本文件
├── LICENSE                       GPL-3.0（继承上游）
├── wnw / refs                    两个 Bash 入口包装器
├── agents/                       4 个角色文档（代劳时必读）
├── scripts/webnovel.py           统一 CLI（preflight / write-gate / chapter-commit / backup …）
├── scripts/data_modules/         状态、索引、向量、RAG、doctor 等实现
├── references/csv/               9 张题材与写法数据表
├── references/                   共享约束、书评 schema、题材画像、加载地图
├── templates/genres/             按题材的初始模板
└── skills/
    ├── webnovel-autopilot/       编排层
    ├── webnovel-init/ plan/ write/ review/ query/ learn/ dashboard/ doctor/
```

## 已知限制（记录一次，别每次重新排查）

- **未配置 `EMBED_API_KEY` 属于「预期降级」，不是故障**：`projection_status.vector` 落 `skipped`，不会再让 `doctor` / `write-gate` 误报失败。提交章节时跳过远端向量化，但仍把 summary / 事件 / 场景 / 实体写入本地 `.webnovel/vectors.db` 并建 BM25 索引，**跨章检索依旧可用、全程不联网**。
- BM25 用「中文单字 + 相邻二元组」分词（无 jieba），召回够用但语义联想弱于向量；`RERANK_API_KEY` 同样缺失 → 无精排。设 `WEBNOVEL_DISABLE_VECTOR=1` 可强制纯 BM25。
- 接续历史项目时，若旧章节没有向量内容行，补跑一次
  `projections replay --from-chapter 1 --to-chapter N` 建立本地索引（幂等，可重复执行）。
- 各书项目各自维护 git 仓库，`backup` 必须以解析后的 `PROJECT_ROOT` 为准，禁止在工作区父目录执行裸全量 `git add`。

## 硬规则

- 禁止并步、跳步、伪造审查、伪造 commit。
- **大纲即法律**：正文不得偏离卷细纲，想改剧情先改大纲。
- **设定即物理**：能力/境界/已发生事实不可回退；写错了改正文，不改设定。
- 审查只跑一轮；blocking 定点修复后直接进下一步。
- 失败只补跑失败步骤，不回退已完成步骤。

## 许可

[GPL-3.0](./LICENSE)。本包移植自上游 `webnovel-writer 6.2.1`，任何再分发需同样遵循 GPL-3.0。

## 与本地安装同步

本地技能装在 `~/.workbuddy/skills/webnovel-writer`。改完本目录后：

```bash
# 覆盖到本地（保留各自项目数据在各自的书目录，不在技能目录里）
cp -r webnovel-writer/* ~/.workbuddy/skills/webnovel-writer/
```

反向同步（把本地改动带回本仓库）同理，注意排除 `__pycache__/`、`.pytest_cache/`、`.coverage` 等开发产物。
