---
name: webnovel-autopilot
description: 网文自动连写编排层。该技能用于在无人值守模式下连续推进一本书：自动探测断点后反复调度 webnovel-writer 的 init / plan / write 命令，逐章循环直到本卷写完或达到指定章数，并在干净断点处停下以便下次续跑。当用户要求「自动写完这一卷」「批量写 N 章」「接着跑」「继续写」「一句话创意直接写成一本书」时使用。需要精细控制单章、单独审查、查询设定或调整某一卷规划时，改用 webnovel-writer。
agent_created: true
---

# Webnovel Autopilot：自动连写编排层

## 定位

这是**编排层**，不重写 `webnovel-writer` 的任何内部逻辑。真正干活的永远是底层 skill 文档所描述的流程；本 skill 只负责：

1. 把用户的一句话创意扩写成 `webnovel-init` 需要的结构化输入；
2. 自动依次调度 init → plan(卷N) → write(本卷各章) → plan(卷N+1) → write(...) 直到停止条件；
3. 每次调用先探测进度，**从断点续跑**，不重做已完成步骤；
4. 在单次会话的资源预算内尽量多写，预算用尽时停在**干净断点**上，并说明下次怎么接着跑。

**每进入一个新阶段，必须先读对应底层文档再动手**，不要凭印象执行。

| 阶段 | 底层文档 |
|---|---|
| Init | `~/.workbuddy/skills/webnovel-writer/skills/webnovel-init/SKILL.md` |
| Plan | `~/.workbuddy/skills/webnovel-writer/skills/webnovel-plan/SKILL.md` |
| Write | `~/.workbuddy/skills/webnovel-writer/skills/webnovel-write/SKILL.md` |

## 环境准备（每次调用第一步）

WorkBuddy 每次 Bash 调用是独立 shell，环境变量不持久，**每次执行前重设**：

```bash
export WNW="$HOME/.workbuddy/skills/webnovel-writer"
export BOOK="<书目录绝对路径>"

"$WNW/wnw" --project-root "$BOOK" preflight
```

`preflight` 出现 `BLOCKER` 就停下报用户，不要自己写替代逻辑。

---

## 断点探测（每次调用必须先跑，决定从哪一步开始）

```bash
BOOK_ROOT="$("$WNW/wnw" --project-root "$BOOK" where)"
python3 -c "import json; s=json.load(open('$BOOK/.webnovel/state.json',encoding='utf-8')); p=s.get('progress',{}); print('current_chapter:', p.get('current_chapter')); print('target:', s.get('project_info',{}).get('target_chapters')); print('volumes_planned:', [v.get('volume') for v in p.get('volumes_planned',[])])"
```

进度真源优先级：`.story-system/commits/` > `.webnovel/state.json` > `大纲/` 与 `正文/` 文件名扫描。**不要用 `正文/` 目录的章节数当作已入账章数**，可能存在写了但没 commit 的章节。

### 阶段判定

| 条件 | 进入 |
|---|---|
| `where` 失败，或无 `.webnovel/state.json` | 阶段 A：Init |
| 当前卷缺 `大纲/第{N}卷-详细大纲.md`，或卷号不在 `volumes_planned` | 阶段 B：Plan |
| 上述都满足，未达 target | 阶段 C：Write 循环 |
| `current_chapter >= target_chapters` 且总纲最后一卷已写完 | 阶段 D：收尾 |

单章级断点用 `run-ledger write-resume --chapter N --mode default --format json` 判断续写 / 重起草 / 只看状态，按它给的建议处理，不要自己猜。

---

## 阶段 A：Init（仅无项目时触发）

读 `skills/webnovel-init/SKILL.md` 按其流程执行，但**输入来源不同**：用户通常只给一句话简介，不是完整结构化表单。

- 由你基于简介自行扩写所需字段（题材、目标规模、故事核、主角欲望/缺陷、反派分层、金手指与代价、卖点等），遵循同一质量标准。
- 只对**真正无法推断且影响全局**的字段用 `AskUserQuestion` 问用户（书名、目标字数、单女主/多女主之类），**最多一轮**。
- 其余字段给合理默认值，完成后告诉用户"这些是我按题材补的，不满意随时改"。
- 禁止因为信息不全卡住不动——缺字段用假设 + 事后告知，不是提前追问。

Init 完成后**不等用户下指令**，直接进入阶段 B 规划卷 1。

## 阶段 B：Plan（每卷开始前触发一次）

读 `skills/webnovel-plan/SKILL.md`，按其 Step 1-10 执行，目标卷号 = 断点探测算出的卷号。

- 跨卷必须做一致性检查（伏笔延续、关系延续、能力不回退）。
- **Step 9/10 的 `master-outline-sync`、`update-state`、Story System 合同刷新必须真正跑完**，这是下一次断点探测能正确工作的前提。

卷规划完成后**不等用户下指令**，直接进入阶段 C。

## 阶段 C：Write 循环（核心，逐章不停）

对 `chapter = 续写起点` 到 `该卷终章` 依次执行：

### C0. prewrite gate 判定树（关键，实测得出）

每章开写前跑：

```bash
"$WNW/wnw" --project-root "$BOOK" write-gate --chapter {N} --stage prewrite --format json
```

按下列顺序判定，**这个顺序不能乱**：

| 判定条件 | 处理 |
|---|---|
| `ok: true` | 正常起草，进 C1 |
| `details.phase.missing_contract_files` 非空 或 blocking_reasons 含「缺少 Story System 合同」 | **真实工作项**：先从卷详细大纲解析本章真实 goal（禁止传占位符），跑 `story-system` 补合同，然后**重跑 gate** |
| `blocking` 仅含 `latest_commit_projection_failed` | **先补跑一次** `projections retry --chapter {上一章}`；重跑 gate 后若返回 `ok: true` 就正常起草。仍失败且 `projection_status` 中有非 `skipped`/`done` 的 `failed:*` 项，才是真实阻断，按下一行走 |
| 其他 blocker | 真实阻断，停止循环，用 `AskUserQuestion` 给 2-3 个有限选项等用户裁决 |

> 为什么不能照搬「一律跳过 prewrite」：跳过会漏掉合同未生成这个真实缺失，导致该章在没有 `chapter_directive` / `forbidden_zones` 约束的情况下裸写——那正是文风崩坏的原因。必须先区分再处理。

### C1. Step 1 上下文

必须使用代劳模式产出写作任务书（规则见 `webnovel-writer` 的主流程代劳模式章节）。**禁止主流程自己拼简版任务书**。

### C2. Step 2 起草

只按任务书写，2000-2500 字（项目另有规定从之）。需要写法参考时用 `"$WNW/refs" --skill write --table <表名> --query "<关键词>"`（注意：**不要传 `--genre`**，会大幅收窄结果）。

### C3. Step 3 审查

代劳 reviewer → 落盘 `.webnovel/tmp/review_results.json` → 跑 `review-pipeline`。审查只跑一轮，blocking 定点修复后直接进下一步，不重复调用 reviewer。

### C4. Step 4 润色

按 `write` 文档的区段读法读 `polish-guide.md`，**7 层 Anti-AI 必须全文逐段检查**（禁止抽样）。输出 `anti_ai_force_check`，为 `fail` 时**不得进入 Step 5**。

### C5. Step 5 提交

代劳 data-agent 产出三份 artifact → `chapter-commit`。

**本章能否继续只以 `chapter-commit` 返回的 `accepted` / `rejected` 为准。**

### C6. Step 6 备份

```bash
"$WNW/wnw" --project-root "$BOOK" backup --chapter {N} --chapter-title "{title}"
```

### C7. 播报并继续

给一句不超过两行的进度播报（第几章 / 章题 / 本卷还剩几章），**然后立刻开始下一章**，不等用户说"继续"。

**不要每章输出完整三段式报告**——太啰嗦。完整报告只在本次调用结束时输出一次，汇总整批章节。

### 停止规则（避免一次调用耗尽资源）

满足任一条件即阶段性收尾（不是失败）：

- 本卷写完 → 规划完下一卷后，**在下一卷第一章正式写之前**停下，汇报"卷{N}已完成，卷{N+1}已规划好，下次从第{X}章开始"；
- 用户指定了章节上限（如"这次只写 5 章"）→ 写满即停；
- 遇到真实阻断（非上表第三类的误判）→ 停下等裁决；
- 达到 `target_chapters` → 阶段 D。

停止时状态必须留在**干净断点**：最后一章已 `accepted` + 已备份，不留半成品正文。

## 阶段 D：全书完成

校验 `current_chapter >= target_chapters` 且总纲最后一卷写完。汇总全书（总章数、总字数、卷数、主线伏笔回收情况），用一次完整报告收尾，提示后续可做：通读校对 / 导出合集 / 投稿准备。

## 中断与续跑

- 不需要额外进度文件——`.story-system/commits/` + `.webnovel/state.json` + `大纲/` 就是唯一真源。
- 用户重新调用本 skill（哪怕只说"继续"），第一步永远是断点探测，不用用户记住进度。
- 想中途停下时让当前这一章跑完，不要在章节中途打断。

## 最终报告（每次调用结束时输出一次）

```text
总状态：已完成本批 / 全书已完成 / 需要你处理。

一、本次完成的内容
- 卷/章范围：第{N}卷 第{a}-{b}章
- 产出文件：正文 / 审查报告 / artifacts / 备份 是否齐全
- 全书进度：第{current}章 / 共{target}章

二、过程中的问题
- 已自动处理：...
- 建议确认：...（新角色暂名、非阻断审查建议）
- 必须处理：...（真正的 BLOCKER，如果有）

三、下一步
- 再调用一次本 skill（或回复"继续"）即可从第{next}章接着写
```

## 硬规则

- 不跳过 write / 审查 / 事实提取 / 提交 / 备份的任何一步，即使是代劳模式。
- 不为了连续写而伪造审查结果、跳过 `chapter-commit`、或放宽"大纲即法律""设定即物理"。
- 每章字数、禁区、必须覆盖节点仍按各卷详细大纲执行，不因为是自动循环就简化。
- plan 的 Step 9/10 与 write 的 Step 5/6 是完整性的底线，任何情况下不得合并或省略。

## 已知缺陷（实测确认，永久生效，不要每次重新排查）

- 本机**未配置 `EMBED_API_KEY`**，但这已**不再是缺陷**：`vector` projection 落 `skipped` 而非 `failed:store_failed`，因此不会污染 `doctor` / `write-gate` 的判定（修复见 `webnovel-writer` 的 vector_projection_writer + rag_adapter）。
- 副作用：跨章检索走本地 BM25（中文单字 + 二元组），**能用但弱于语义检索**。不要把「RAG 没召回」当作「设定不存在」的依据——此时应以 Story System 合同、`previous_summaries`、`.webnovel/summaries` 为准。
- 首次接续一个历史项目时，若 `.webnovel/vectors.db` 里旧章节没有内容行（跨章召回为空），补跑一次 `projections replay --from-chapter 1 --to-chapter N` 建立本地索引；幂等，可重复执行。
- 将来用户配置了 `EMBED_API_KEY` 并明确要恢复语义检索时：在项目根写 `.env`，再对该范围重跑一次 `projections replay` 即可，无需改任何判定逻辑。
