# WorkBuddy Skills

个人 WorkBuddy 技能合集。每个子目录是一个独立技能，可单独安装，也可整仓克隆。

> 平台：Windows（其余平台未验证）· 技能依赖：仅 Python 3.8+ 标准库（除注明者）
> 第三方来源与许可见 [THIRD-PARTY.md](./THIRD-PARTY.md)

收录原则：**只收模型能主动触发的技能**。上游标了 `disable-model-invocation`（只能用户点名）的一概不装——装了也不会被 AI 自己用起来，只会让技能列表变噪音。

## 技能目录

### 主力技能

| 技能 | 说明 |
|---|---|
| [`workbuddy-history-recovery`](./workbuddy-history-recovery) | 🔍 **会话记录找回与迁移**。换号 / 重装后历史列表为空？记录其实都在本机，此工具把它们迁回当前账号名下，并支持恢复误删、导出 Markdown、数据库备份还原 |
| [`webnovel-writer`](./webnovel-writer) | ✍️ **长篇中文网文创作**。执行层（建书/规划卷/写章/审查/查设定/润色）+ 编排层（无人值守连写整卷）合包，内置一致性合同树、五维事实审查、7 层 Anti-AI 规范、9 张题材写法数据表 |
| [`impeccable`](./impeccable) | 🎨 **前端界面设计**。设计/重做/审查/审计/打磨/适配/动效/配色/排版，覆盖落地页、后台、仪表盘、组件、空状态 |
| [`qu-ai`](./qu-ai) | 🪶 **去AI味改写**。31 条模式清掉模板腔与空话，同时锁死事实、数字与限定不被抹掉；可先蒸馏你的写作风格再按该风格改，避免十篇十种口气 |

### 工程实践（移植自 mattpocock/skills，MIT）

15 个，全部为模型可触发，覆盖「写代码」与「通用工作流」。

| 技能 | 说明 |
|---|---|
| [`tdd`](./tdd) | 测试驱动开发：red-green-refactor 循环，一个纵向切片一个切片地建功能/修 bug |
| [`code-review`](./code-review) | 双轴审查：**Standards**（仓库编码规范 + Fowler 异味基线）× **Spec**（是否忠实实现原始需求），并行子代理跑 |
| [`codebase-design`](./codebase-design) | 深模块设计纪律与词汇：小接口、干净接缝、可经接口测试 |
| [`diagnosing-bugs`](./diagnosing-bugs) | 难 bug 与性能回归的诊断循环：先建会红的反馈回路 → 最小化 → 假设 → 插桩 → 修 → 回归测试 |
| [`domain-modeling`](./domain-modeling) | 主动打磨项目领域模型：挑战术语、场景压测、就地更新 `GLOSSARY.md` 与 ADR |
| [`prototype`](./prototype) | 一次性原型回答设计问题：单文件 HTML 表达状态/逻辑，或多版本可切换 UI 变体 |
| [`research`](./research) | 对着高可信一手来源调研问题，结论写成带引用的 Markdown 落库（后台代理跑） |
| [`pr`](./pr) | PR 正文该有的形状：最小可视化摘要 + 前后对比证据 + 合并风险判断（单向门/双向门 + 影响面） |
| [`wizard`](./wizard) | 生成交互式 bash 向导，带人走只有人能做的步骤：开基础设施、配凭证/CI 密钥、跑一次性迁移 |
| [`grilling`](./grilling) | relentlessly 追问一个计划/决策/想法，直到设计树每个分支都定下来 |
| [`writing-for-agents`](./writing-for-agents) | 写给代理看的文档：skills、AGENTS.md/CLAUDE.md，以及任何代理按指针去读的东西 |
| [`git-guardrails-claude-code`](./git-guardrails-claude-code) | 配 hooks 拦下危险 git 命令（push / `reset --hard` / `clean`）。⚠️ 上游面向 Claude Code，WorkBuddy 无对应 hooks 机制 |
| [`setup-pre-commit`](./setup-pre-commit) | 配 Husky pre-commit + lint-staged + Prettier + 类型检查 + 测试 |
| [`scaffold-exercises`](./scaffold-exercises) | 建练习目录结构（sections/problems/solutions/explainers），场景较窄 |
| [`migrate-to-shoehorn`](./migrate-to-shoehorn) | 把测试的 `as` 断言迁到 `@total-typescript/shoehorn`，场景较窄 |

## 安装

### 方式一：装单个技能

把对应技能目录整个复制到用户级技能目录：

```powershell
# Windows PowerShell，示例：tdd
robocopy "<仓库路径>\tdd" "$env:USERPROFILE\.workbuddy\skills\tdd" /E
```

```bash
# macOS / Linux
cp -r workbuddy-skills/tdd ~/.workbuddy/skills/
```

### 方式二：整仓克隆，按需挑选

```bash
git clone git@github.com:dlzbm/workbuddy-skills.git
```

工程实践那 15 个可以一次全装：

```bash
for d in tdd code-review codebase-design diagnosing-bugs domain-modeling prototype research pr wizard \
         grilling writing-for-agents git-guardrails-claude-code setup-pre-commit \
         scaffold-exercises migrate-to-shoehorn; do
  cp -r "workbuddy-skills/$d" ~/.workbuddy/skills/
done
```

装好后在 WorkBuddy 对话里直接说人话即可触发（每个技能的触发词见其 SKILL.md 的 description）。

## 目录结构

```
workbuddy-skills/
├── README.md                 ← 本文件：简介 + 技能索引
├── THIRD-PARTY.md            ← 第三方来源与许可明细
├── LICENSE
├── webnovel-writer/          ← 一个子目录 = 一个技能
│   ├── README.md
│   ├── SKILL.md
│   ├── scripts/
│   └── skills/               ← 该技能自带的子技能
└── tdd/ code-review/ …        ← 其余技能同构
```

## 新增技能

在根目录新建一个子目录，遵循上述结构（`SKILL.md` + `README.md` + 可选 `scripts/`、`references/`），并在上方表格里加一行即可。

## 许可证

外层脚手架与自制技能：[MIT](./LICENSE)。
移植技能的许可各不相同（GPL-3.0 / Apache-2.0 / MIT），逐个列在 [THIRD-PARTY.md](./THIRD-PARTY.md)。
