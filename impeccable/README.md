# impeccable（WorkBuddy 移植版）

前端界面设计技能包：从落地页到后台仪表盘，从规划、构建、审查到打磨、适配、性能，覆盖一整套 UI 设计工作流。

> 上游：[pbakaus/impeccable](https://github.com/pbakaus/impeccable) · Apache-2.0
> 技能版本 4.3.1 / engine 0.1.5 · 本副本只改了路径与运行方式，方法内容未动

---

## 它能干什么

不是"写点 CSS"，是把设计任务当成设计总监来做：完整交付、有明确观点、不糊弄。核心原则三条——**全力以赴**（不留半成品，除用户必须提供的素材）、**大胆**（做出有辨识度的东西，不是安全牌）、**有限轮次验证**（最多两轮截图批修，不许无限自嗨打磨）。

## 命令一览

| 命令 | 类别 | 说明 |
|---|---|---|
| `init` | 构建 | 采集产品上下文，写入 PRODUCT.md |
| `document` | 构建 | 从现有代码反推生成 DESIGN.md |
| `shape [feature]` | 构建 | 写代码前先规划 UX/UI |
| `extract [target]` | 构建 | 把可复用 token / 组件抽成设计系统 |
| `critique [target]` | 评估 | UX 设计评审 + 启发式打分 |
| `audit [target]` | 评估 | 技术质量检查：可访问性、性能、响应式 |
| `polish [target]` | 打磨 | 上线前最后一轮质量把关 |
| `bolder` / `quieter` | 打磨 | 放大平淡的设计 / 压住吵闹的设计 |
| `distill [target]` | 打磨 | 做减法，回到本质 |
| `harden [target]` | 打磨 | 生产化：错误态、i18n、边界情况 |
| `onboard [target]` | 打磨 | 首次使用流程、空状态、激活引导 |
| `animate` / `colorize` / `typeset` / `layout` | 增强 | 动效 / 配色 / 字体层级 / 间距节奏 |
| `delight` / `overdrive` | 增强 | 加个性记忆点 / 突破常规上限 |
| `clarify` / `adapt` / `optimize` | 修复 | 文案与报错 / 多设备适配 / 性能诊断 |
| `live` | 迭代 | 浏览器里框选元素，生成视觉变体 |
| `doctor` | 维护 | 检查并修复产物与当前版本的漂移 |
| `hooks <on\|off\|status\|…>` | 维护 | 编辑 UI 文件后自动跑设计检测器 |

不带参数直接调用会弹出上下文菜单，不会自动跑某条命令。

## 安装

本地已装在 `~/.workbuddy/skills/impeccable`。从仓库安装：

```powershell
# Windows PowerShell
robocopy "<仓库路径>\impeccable" "$env:USERPROFILE\.workbuddy\skills\impeccable" /E
```

```bash
# macOS / Linux
cp -r impeccable ~/.workbuddy/skills/
```

## 用法

每次会话先跑一次 context（cwd 保持在你的项目里）：

```bash
# Git Bash
~/.workbuddy/skills/impeccable/scripts/impeccable context

# cmd / PowerShell
C:\Users\<你>\.workbuddy\skills\impeccable\scripts\impeccable.cmd context
```

然后按 SKILL.md 的三步 Setup 走：加载对应命令的 playbook → 动手改 UI 前先读
`reference/craft-floor.md`（质量底线与绝对禁令）。

## WorkBuddy 移植差异（4 点，详见 SKILL.md 顶部）

1. **基础目录**统一为 `~/.workbuddy/skills/impeccable`；原文里所有 `.agents/skills/impeccable` 路径已批量替换。
2. **命令调用**走技能目录下的 launcher（`scripts/impeccable` 或 `scripts/impeccable.cmd`）。
3. **Engine 二进制**：首次运行按 `scripts/VERSION` 从 GitHub Releases 下载并校验 sha256，缓存在
   `~/.impeccable/bin/<version>/`。本机直连 GitHub 容易被代理掐断，先设镜像：
   ```bash
   export IMPECCABLE_DOWNLOAD_BASE="https://ghfast.top/https://github.com/pbakaus/impeccable/releases/download"
   ```
   下载不了也能用——按 SKILL.md 的 "Launcher unavailable" 分支，直接读项目里已有的 PRODUCT.md / DESIGN.md。
4. **子代理代劳**：WorkBuddy 的 Agent 工具不支持自定义子代理类型，4 个子代理改为「主流程读
   `reference/degraded/*.md` 内联代劳」，角色定义见 `agents/*.md`，产出文件与 schema 保持一致。

## 目录结构

```
impeccable/
├── SKILL.md                 入口（顶部是本移植说明，下面是上游原文）
├── README.md                本文件
├── scripts/impeccable(.cmd) launcher：按需下载并 exec engine 二进制
├── scripts/data/font-index.json   字体索引（1.1MB，别删）
├── scripts/live-browser*.js        live 模式的浏览器端脚本
├── agents/                  4 个子代理角色定义（.toml 原文件 + 转换出的 .md）
└── reference/               各命令的 playbook
    ├── craft-floor.md       动手改 UI 前必读：质量底线、绝对禁令
    ├── new-work.md          新界面 / 换视觉世界（52KB，按需分段读）
    ├── critique.md audit.md live.md document.md …
    └── degraded/            无子代理环境下的等价流程（代劳时读这些）
```

## 已知注意

- `live` 与 `hooks` 依赖浏览器环境和本机权限，跑不起来不影响其余命令。
- `font-index.json` 与 `live-browser.js` 体积大（合计约 1.6MB），是运行时数据，不是冗余文件。

## 许可

上游 [Apache-2.0](https://github.com/pbakaus/impeccable/blob/main/LICENSE)。再分发需保留许可与声明。
