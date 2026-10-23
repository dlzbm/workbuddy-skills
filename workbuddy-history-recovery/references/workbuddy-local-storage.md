# WorkBuddy 桌面端本地存储结构

本机 `%USERPROFILE%\.workbuddy\` 下的关键路径与含义。排查「记录不见了」类问题时按此表定位。

## 会话与索引

| 路径 | 内容 | 是否与账号绑定 |
|---|---|---|
| `workbuddy.db` | SQLite 主库，`sessions` 表是历史列表的**唯一数据源** | 是（`user_id` 列） |
| `workbuddy.db-wal` / `-shm` | WAL 日志与共享内存。**未 checkpoint 的写入只在这里** | - |
| `projects/<cwd 编码>/<会话ID>.jsonl` | 会话**正文**（完整对话流，JSON Lines） | **否，与账号无关** |
| `projects/<cwd 编码>/<会话ID>.file-rollback.ndjson` | 文件改动回滚记录 | 否 |
| `projects/<cwd 编码>/<会话ID>/tool-results/` | 工具调用大结果落盘 | 否 |
| `projects/<cwd 编码>/<会话ID>/subagents/agent-*.jsonl` | 子代理日志 | 否 |
| `artifact-index/<会话ID>.json` | 该会话产出/触碰过的文件清单 | 否 |
| `file-history/<会话ID>/` | 文件历史快照 | 否 |

`<cwd 编码>` 的规则：把工作目录绝对路径里的 `:`、`\`、`/` 换成 `-`，去掉盘符后的分隔符。
例：`D:\code\project\小说` → `d-code-project-小说`。

## 账号相关

| 路径 | 内容 |
|---|---|
| `storage/skeleton/account-snapshot.json` | 当前登录账号快照，`primary.uid` 即当前 UID |
| `storage/user-<UID>-personal/` | 该账号的个人数据根 |
| `storage/user-<UID>-personal/MEMORY.md` | **用户级长期记忆**（跨工作区） |
| `storage/user-<UID>-personal/scoped/<hash>/conversation-list.json` | 会话列表 UI 缓存（会重新生成，非数据源） |
| `storage/device/` | 设备级共享数据（不分账号） |

## `sessions` 表关键列

| 列 | 说明 |
|---|---|
| `id` | 会话 UUID，对应 `<会话ID>.jsonl` 的文件名 |
| `cwd` | 工作目录，决定正文落在哪个 `projects/<编码>/` 下 |
| `user_id` | **归属账号 UID。历史列表按此过滤** |
| `title` / `custom_title` | 自动标题 / 用户改名 |
| `deleted_at` | 删除时间戳（ms）。`NULL` / `-1` 表示未删除 |
| `is_playground` | 1 = 实验场会话，不进正式历史列表 |
| `transport` | `local` = 纯本地；`cloud` = 云端同步 |
| `project_id` | 云端团队项目 ID，跨账号迁移时必须清空 |
| `status` | `working` / `completed` / `error` / `terminated` |

## 已知坑

1. **校验时必须连 WAL 一起复制。**
   只复制 `workbuddy.db` 会读到未 checkpoint 的旧快照，误判「迁移没生效」。
   正确做法：同时复制 `workbuddy.db`、`workbuddy.db-wal`、`workbuddy.db-shm` 到同一目录再打开。
   直接连原库读则无需特殊处理，SQLite 会自动合并 WAL。

2. **客户端运行中也能改库，但列表要重启才刷新。**
   连接时设 `PRAGMA busy_timeout` 避免 `SQLITE_BUSY`。改完需完全退出客户端（含托盘）再开。

3. **换号后旧记录消失 ≠ 数据丢失。**
   正文文件和 `projects/` 目录都不动，只是 `sessions.user_id` 对不上。

4. **正文存在但索引不存在** 的会话（`doctor` 里报「无索引的正文」）：
   可以正常导出，但界面永远不会显示。反向情况是索引在、正文被删（`doctor` 报「会话文件缺失」）。

5. **`logs/`、`cache/`、`sessions/`（进程心跳）、`traces/`** 与历史记录无关，别去那里找。
