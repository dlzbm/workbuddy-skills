# WorkBuddy Skills

个人 WorkBuddy 技能合集。每个子目录是一个独立技能，可单独安装，也可整仓克隆。

> 平台：Windows（其余平台未验证）· 技能依赖：仅 Python 3.8+ 标准库（除注明者）
> 第三方来源与许可见 [THIRD-PARTY.md](./THIRD-PARTY.md)

## 技能目录

### 主力技能

| 技能 | 说明 |
|---|---|
| [`workbuddy-history-recovery`](./workbuddy-history-recovery) | 🔍 **会话记录找回与迁移**。换号 / 重装后历史列表为空？记录其实都在本机，此工具把它们迁回当前账号名下，并支持恢复误删、导出 Markdown、数据库备份还原 |
| [`webnovel-writer`](./webnovel-writer) | ✍️ **长篇中文网文创作**。执行层（建书/规划卷/写章/审查/查设定/润色）+ 编排层（无人值守连写整卷）合包，内置一致性合同树、五维事实审查、7 层 Anti-AI 规范、9 张题材写法数据表 |
| [`impeccable`](./impeccable) | 🎨 **前端界面设计**。设计/重做/审查/审计/打磨/适配/动效/配色/排版，覆盖落地页、后台、仪表盘、组件、空状态 |

### 工程实践（engineering，移植自 mattpocock/skills，MIT）

20 个技能，覆盖「写代码」全流程。**触发**列标明是模型可自动选用，还是只在用户点名时执行。

| 技能 | 说明 | 触发 |
|---|---|---|
| [`tdd`](./tdd) | 测试驱动开发：red-green-refactor 循环，一个纵向切片一个切片地建功能/修 bug | 模型可触发 |
| [`code-review`](./code-review) | 双轴审查：**Standards**（仓库编码规范 + Fowler 异味基线）× **Spec**（是否忠实实现原始需求），并行子代理跑 | 模型可触发 |
| [`codebase-design`](./codebase-design) | 深模块设计纪律与词汇：小接口、干净接缝、可经接口测试 | 模型可触发 |
| [`diagnosing-bugs`](./diagnosing-bugs) | 难 bug 与性能回归的诊断循环：先建会红的反馈回路 → 最小化 → 假设 → 插桩 → 修 → 回归测试 | 模型可触发 |
| [`domain-modeling`](./domain-modeling) | 主动打磨项目领域模型：挑战术语、场景压测、就地更新 `GLOSSARY.md` 与 ADR | 模型可触发 |
| [`prototype`](./prototype) | 一次性原型回答设计问题：单文件 HTML 表达状态/逻辑，或多版本可切换 UI 变体 | 模型可触发 |
| [`research`](./research) | 对着高可信一手来源调研问题，结论写成带引用的 Markdown 落库（后台代理跑） | 模型可触发 |
| [`pr`](./pr) | PR 正文该有的形状：最小可视化摘要 + 前后对比证据 + 合并风险判断（单向门/双向门 + 影响面） | 模型可触发 |
| [`wizard`](./wizard) | 生成交互式 bash 向导，带人走只有人能做的步骤：开基础设施、配凭证/CI 密钥、跑一次性迁移 | 模型可触发 |
| [`ask-matt`](./ask-matt) | 路由器：问「我这个场景该用哪个技能/流程」，在上面的用户调用型技能里挑 | 仅用户调用 |
| [`grill-with-docs`](./grill-with-docs) | 盘问式会话，顺带把项目领域模型建起来，就地打磨术语并更新 `GLOSSARY.md` / ADR | 仅用户调用 |
| [`triage`](./triage) | 让 issue 走一套 triage 角色状态机 | 仅用户调用 |
| [`improve-codebase-architecture`](./improve-codebase-architecture) | 扫代码库找「加深」机会，输出可视化 HTML 报告，然后逐条盘问 | 仅用户调用 |
| [`setup-matt-pocock-skills`](./setup-matt-pocock-skills) | 给仓库做一次性配置（issue tracker、triage 标签、领域文档布局），是其它 tracker 型技能的前置 | 仅用户调用 |
| [`to-spec`](./to-spec) | 把当前对话整理成 spec 并发到 issue tracker | 仅用户调用 |
| [`to-tickets`](./to-tickets) | 把任意计划/spec/对话拆成一串 tracer-bullet ticket，声明阻塞边 | 仅用户调用 |
| [`implement`](./implement) | 按 spec 或 ticket 集施工：约定好的接缝处驱动 `/tdd`，提交前用 `/code-review` 收尾 | 仅用户调用 |
| [`implement-spec`](./implement-spec) | 在一条集成分支上实现整份 spec：ticket 当任务图，就绪前沿上并行跑实现子代理 | 仅用户调用 |
| [`wayfinder`](./wayfinder) | 规划超出单次会话容量的大工程：在 tracker 上铺一张决策 ticket 地图，逐个解决直到路径清晰 | 仅用户调用 |
| [`retro`](./retro) | 会后给编码代理的环境提改进建议（导航、自动化检查、编码规范、steering 文件、工具链），按严重度排序 | 仅用户调用 |

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

工程实践那 20 个可以一次全装：

```bash
for d in tdd code-review codebase-design diagnosing-bugs domain-modeling prototype research pr wizard \
         ask-matt grill-with-docs triage improve-codebase-architecture setup-matt-pocock-skills \
         to-spec to-tickets implement implement-spec wayfinder retro; do
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
