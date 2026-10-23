---
name: workbuddy-history-recovery
description: 排查、找回与迁移 WorkBuddy 桌面端的本地会话记录。当用户反馈「换号/换账号后历史记录不见了」「办公记录没了」「历史列表是空的」、「想找回被删除的对话」、「把旧账号的记录迁到当前账号」、「导出某次对话/导出历史记录」、「某个会话的本地文件在哪」，或需要备份/还原 workbuddy.db 时使用。核心原理：会话正文按工作目录存盘、与账号无关，界面历史列表由 workbuddy.db 的 sessions.user_id 过滤。
agent_created: true
---

# WorkBuddy 会话记录找回与迁移

## 核心事实（先记住这三条）

1. 客户端历史列表**不是**读文件目录，而是查 `~/.workbuddy/workbuddy.db` 的 `sessions` 表，按 `user_id` 过滤。
2. 会话**正文**按工作目录存盘在 `~/.workbuddy/projects/<cwd 编码>/<会话ID>.jsonl`，**与账号无关，换号不会删**。
3. 所以「换号后记录不见了」几乎总是 `sessions.user_id` 不匹配造成的，**不是数据丢失**。

详细的目录结构与表结构见 `references/workbuddy-local-storage.md`。

## 工作流

### 第一步：诊断，不要上来就改

```bash
python scripts/wb_history.py doctor   # 自检：索引与正文是否一致
python scripts/wb_history.py list     # 列出全部会话，按账号 UID 分组
```

`list` 会明确标出「当前账号」与其他账号各有几条，并给出一句小结。
如果其他账号下有若干未删除的会话，就是它们被账号过滤掉了 —— 走第二步。
如果正文文件也缺失，那才是真丢数据，只能靠备份还原。

**先向用户确认要迁移哪些**，把 `list` 的结果呈现给他，尤其是「已删除」和「playground」那两类。

### 第二步：迁移归属

```bash
python scripts/wb_history.py recover              # 预演，只打印不写库
python scripts/wb_history.py recover --apply      # 确认后执行
```

- 默认只迁 `transport = local` 且未删除的会话，这是用户真正「丢了」的那批。
- `--include-deleted` 连同此前被用户删掉的会话一起恢复。
- `--include-cloud` 连云端 playground 会话一起改（一般不需要）。
- `--only <id前缀,id前缀>` / `--skip <id前缀>` 精确挑选。
- 脚本会自动：备份数据库 → 改 `user_id` → 清空指向旧账号的 `project_id`。

**改完必须让用户完全退出 WorkBuddy（含托盘图标）再打开**，否则列表不会刷新。这是最容易漏的一步，务必提醒。

### 第三步：验证

迁移脚本会打印目标账号的会话总数。若用户重启后仍看不到，重跑一次 `recover --apply` 即可（脚本是幂等的，只会处理仍挂在其他 UID 下的行）。

## 其他子命令

```bash
# 找某个会话的本地正文文件
python scripts/wb_history.py locate <会话ID前缀>

# 导出为可读 Markdown（默认输出到 cwd）
python scripts/wb_history.py export <会话ID前缀> -o out.md --tools

# 列出 / 还原数据库备份
python scripts/wb_history.py backups
python scripts/wb_history.py backups --restore 20261015-153414 --apply

# 恢复被删除的会话（只清 deleted_at，不改归属）
python scripts/wb_history.py undelete <会话ID前缀> --apply
```

`export` 会自动剥掉 `<system-reminder>`、`<identity_context>` 等注入噪声，只保留真实对话。

## 安全约束

- **写操作一律先预演。** 所有带 `--apply` 的动作都要用户确认后才执行，且脚本会先自动备份 `workbuddy.db`（含 `-wal` / `-shm`）。
- **绝不删除任何会话行或 `.jsonl` 文件。** 本技能只改 `user_id` / `deleted_at` / `project_id` 三个字段。用户要「清理」时也要先给清单再确认。
- **不要迁移 `transport = cloud` 的会话**，除非用户明确要求；那类记录的归属由服务端决定，改了可能被同步回去。
- **改库前确认客户端状态。** 运行中改库可行（脚本已设 `busy_timeout`），但必须提醒用户重启客户端才能看到效果。

## 常见误判

| 现象 | 真因 |
|---|---|
| 复制 `workbuddy.db` 单独打开，发现改动没了 | 写入还在 `workbuddy.db-wal` 里，必须连 WAL 一起复制 |
| 改了 `user_id`，重启后列表还是空 | 客户端没完全退出，或列表缓存未重建 |
| `doctor` 报「无索引的正文」 | `.jsonl` 在但 `sessions` 表没这行，可导出但界面不显示 |
| `doctor` 报「会话文件缺失」 | 索引在但 `.jsonl` 被删，属于真丢失，只能从备份恢复 |
