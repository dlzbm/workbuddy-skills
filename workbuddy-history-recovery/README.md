# workbuddy-history-recovery

WorkBuddy 桌面端**本地会话记录找回与迁移**工具。

一句话：换号 / 重装之后，客户端历史列表空了？记录其实都还在本机，这个工具负责把它们找回来、迁到当前账号名下，并能导出成可读文档。

> 适用平台：Windows（macOS / Linux 理论可用，路径写法不同，未测试）
> 依赖：仅 Python 3.8+ 标准库，无需安装任何第三方包

---

## 背景：为什么"记录不见了"却不是真丢了

WorkBuddy 桌面端把数据分两层存：

| 层 | 位置 | 是否绑定账号 |
|---|---|---|
| **正文**（完整对话流） | `~/.workbuddy/projects/<工作目录编码>/<会话ID>.jsonl` | ❌ 与账号无关 |
| **索引**（历史列表） | `~/.workbuddy/workbuddy.db` 的 `sessions` 表 | ✅ 按 `user_id` 过滤 |

登录新账号后，界面历史列表按 `sessions.user_id = 当前UID` 过滤，旧会话的 `user_id` 还是旧账号的 UID —— 于是列表为空。

**但 `.jsonl` 正文一个字节都没动。** 只要改回 `user_id`，记录立刻回来。本工具做的就是这个，外加恢复误删、导出、备份还原。

```
~/.workbuddy/
├── workbuddy.db                  ← sessions 表：历史列表唯一数据源（user_id 过滤）
├── workbuddy.db-wal / -shm       ← WAL 日志，未 checkpoint 的写在这里
└── projects/
    ├── d-code-project-小说/
    │   ├── 5998b1ff-….jsonl      ← 会话正文（真实对话流）
    │   └── 5998b1ff-….file-rollback.ndjson
    └── d-code-project-药店药品比价监管平台/
        └── …
```

---

## 功能

| 子命令 | 作用 |
|---|---|
| `doctor` | 自检：数据库、当前 UID、正文文件与索引是否一致、缺失/孤儿统计 |
| `list` | 按账号 UID 分组列出**全部**会话（含界面看不到的），标注已删除/云端/playground |
| `locate` | 按会话 ID 前缀定位 `.jsonl` 正文文件的完整路径 |
| `recover` | **核心功能**：把其他账号名下的会话迁移到当前账号 |
| `undelete` | 恢复被删除的会话（清空 `deleted_at`） |
| `export` | 把会话导出为干净的 Markdown 文档（自动剥离系统注入噪声） |
| `backups` | 列出 / 还原 `workbuddy.db` 自动备份 |

## 安全设计

- **所有写操作默认预演**，只打印将要做的事，必须显式加 `--apply` 才落盘
- 每次写库前**自动备份** `workbuddy.db`（连 `-wal` / `-shm` 一起）
- 只改 `user_id` / `deleted_at` / `project_id` **三个字段**，绝不 `DELETE` 会话行、绝不删 `.jsonl`
- 默认**不碰云端会话**（`transport = cloud`），避免与服务端同步冲突
- 迁移时自动清空指向旧账号项目的 `project_id`，防止列表异常

---

## 安装

### 方式一：装成 WorkBuddy 技能（推荐）

把本仓库整个目录复制到用户级技能目录：

```powershell
# Windows PowerShell
robocopy "$env:TEMP\workbuddy-history-recovery" "$env:USERPROFILE\.workbuddy\skills\workbuddy-history-recovery" /E
```

```bash
# macOS / Linux
cp -r workbuddy-history-recovery ~/.workbuddy/skills/
```

装好后，在 WorkBuddy 里直接说人话即可触发，例如：

- 「我换号了，之前的记录不见了」
- 「把旧账号的会话迁到当前账号」
- 「列出本机所有会话」「导出那次 xxx 的对话」「恢复我删掉的对话」

### 方式二：当作独立脚本用

```bash
git clone git@github.com:dlzbm/workbuddy-history-recovery.git
python workbuddy-history-recovery/scripts/wb_history.py --help
```

---

## 使用

### 1️⃣ 先诊断，别上来就改

```bash
python scripts/wb_history.py doctor
python scripts/wb_history.py list
```

`list` 输出示例：

```
当前登录 UID：28dcc2c9-…
============================================================================
账号 8dcd2158…  共 14 条（未删除 9 条）
============================================================================
  72a42863  2026-09-23 10:39  优化整理前端开发简历
            D:\文档\简历
  …

小结：当前账号 2 条；其他账号 14 条（这些在界面上看不到，可用 recover 迁移）
```

「其他账号」那批未删除的会话，就是被账号过滤掉、界面看不到的记录。

### 2️⃣ 迁移到当前账号

```bash
python scripts/wb_history.py recover              # 预演
python scripts/wb_history.py recover --apply      # 确认无误后执行
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--from <UID>` | 只迁指定源账号（默认所有非当前账号） |
| `--only <前缀,前缀>` | 只迁这些会话（ID 前缀即可） |
| `--skip <前缀,前缀>` | 跳过某些会话 |
| `--include-deleted` | 连同此前删除的会话一起恢复 |
| `--include-cloud` | 连云端 playground 会话一起改（慎用） |

### 3️⃣ 重启客户端（关键一步）

**完全退出 WorkBuddy（含托盘图标）再打开**，历史列表才会刷新。这一步最容易漏。

脚本是幂等的：如果重启后列表还是空，直接再跑一次 `recover --apply` 即可。

### 4️⃣ 其他常用操作

```bash
# 定位某个会话的本地正文
python scripts/wb_history.py locate b6fb9de6

# 导出成 Markdown（自动剥离 <system-reminder> 等注入噪声）
python scripts/wb_history.py export b6fb9de6 -o 药店平台调试记录.md --tools

# 恢复误删的会话
python scripts/wb_history.py undelete e2260fba --apply

# 数据库备份管理
python scripts/wb_history.py backups
python scripts/wb_history.py backups --restore 20261015-153414 --apply
```

---

## 常见问题（FAQ）

<details>
<summary><b>Q：迁移后重启了，列表还是空的？</b></summary>

1. 确认是真·完全退出：系统托盘图标也要退掉。
2. 重跑 `recover --apply`（幂等，只会处理仍挂在旧 UID 下的行）。
3. 跑 `doctor` 看正文与索引是否一致。
</details>

<details>
<summary><b>Q：验证时复制了 workbuddy.db 单独打开，发现改动"没生效"？</b></summary>

不是没生效。最近的写入还在 `workbuddy.db-wal` 里，**必须连 `-wal` / `-shm` 一起复制**再打开，否则读到的是旧快照。直接连原库读则无此问题（SQLite 自动合并 WAL）。
</details>

<details>
<summary><b>Q：doctor 报"无索引的正文"？</b></summary>

`.jsonl` 在但 `sessions` 表没这一行，可以正常 `export`，但界面永远不会显示。
</details>

<details>
<summary><b>Q：doctor 报"会话文件缺失"？</b></summary>

索引在但 `.jsonl` 被删了，属于真丢失，只能从 `backups` 还原或接受现实。
</details>

<details>
<summary><b>Q：会不会把我的记录搞丢？</b></summary>

工具本身没有删除能力：不 `DELETE` 行、不删文件，只 `UPDATE` 三个字段，且每次写前自动备份。最坏情况用 `backups --restore` 回滚。
</details>

---

## 目录结构

```
workbuddy-history-recovery/
├── README.md                            ← 本文件
├── SKILL.md                             ← WorkBuddy 技能入口（触发条件 + 工作流 + 安全约束）
├── scripts/
│   └── wb_history.py                    ← 主工具，仅依赖标准库
└── references/
    └── workbuddy-local-storage.md       ← ~/.workbuddy 目录结构与表结构详解
```

## 许可证

[MIT](LICENSE)
