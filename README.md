# WorkBuddy Skills

个人 WorkBuddy 技能合集。每个子目录是一个独立技能，可单独安装，也可整仓克隆。

> 平台：Windows（其余平台未验证）· 依赖：各技能仅用 Python 3.8+ 标准库

## 技能目录

| 技能 | 说明 |
|---|---|
| [`workbuddy-history-recovery`](./workbuddy-history-recovery) | 🔍 **会话记录找回与迁移**。换号 / 重装后历史列表为空？记录其实都在本机，此工具把它们迁回当前账号名下，并支持恢复误删、导出 Markdown、数据库备份还原 |

## 安装

### 方式一：装单个技能

把对应技能目录整个复制到用户级技能目录：

```powershell
# Windows PowerShell，示例：workbuddy-history-recovery
robocopy "<仓库路径>\workbuddy-history-recovery" "$env:USERPROFILE\.workbuddy\skills\workbuddy-history-recovery" /E
```

```bash
# macOS / Linux
cp -r workbuddy-skills/workbuddy-history-recovery ~/.workbuddy/skills/
```

### 方式二：整仓克隆，按需挑选

```bash
git clone git@github.com:dlzbm/workbuddy-skills.git
```

装好后在 WorkBuddy 对话里直接说人话即可触发对应技能（每个技能的触发词见其 README / SKILL.md）。

## 目录结构

```
workbuddy-skills/
├── README.md                                 ← 本文件：简介 + 技能索引
├── LICENSE
└── workbuddy-history-recovery/               ← 一个子目录 = 一个技能
    ├── README.md                             ← 该技能的完整说明
    ├── SKILL.md                              ← WorkBuddy 技能入口
    ├── scripts/
    └── references/
```

## 新增技能

在根目录新建一个子目录，遵循上述结构（`SKILL.md` + `README.md` + 可选 `scripts/`、`references/`），并在上方「技能目录」表格里加一行即可。

## 许可证

[MIT](./LICENSE)
