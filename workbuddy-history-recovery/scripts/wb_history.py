#!/usr/bin/env python3
"""
WorkBuddy 本地会话记录工具。

用途：
  - list      列出本机所有会话（按账号 UID 分组），定位「记录不见了」的原因
  - locate    按会话 ID 前缀找到对应的 .jsonl 正文文件
  - recover   把旧账号名下的会话迁移到当前账号（改 sessions.user_id），让界面重新显示
  - undelete  恢复被删除的会话（清空 deleted_at）
  - export    把会话导出为可读 Markdown
  - backups   列出 / 还原数据库备份

只依赖 Python 标准库。写操作默认是「预演」，必须显式 --apply 才落盘。
"""

import argparse
import datetime
import glob
import json
import os
import re
import shutil
import sqlite3
import sys
import time

HOME = os.environ.get("USERPROFILE") or os.path.expanduser("~")
WB = os.path.join(HOME, ".workbuddy")
DB = os.path.join(WB, "workbuddy.db")
PROJECTS = os.path.join(WB, "projects")
SNAPSHOT = os.path.join(WB, "storage", "skeleton", "account-snapshot.json")

NOISE_TAGS = (
    "system-reminder", "identity_context", "project_context", "memory",
    "task-notification", "local-command-stdout", "wecom_wedrive_references",
)


# ---------------------------------------------------------------- 基础工具

def ts(v):
    if v in (None, -1, 0):
        return "-"
    try:
        return datetime.datetime.fromtimestamp(int(v) / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(v)


def current_uid():
    """从客户端账号快照里读当前登录 UID。"""
    try:
        with open(SNAPSHOT, "r", encoding="utf-8") as f:
            return json.load(f)["primary"]["uid"]
    except Exception:
        pass
    # 退路：个人目录 user-<uid>-personal
    for d in glob.glob(os.path.join(WB, "user-*-personal")):
        n = os.path.basename(d)
        m = re.match(r"user-(.+?)-personal$", n)
        if m:
            return m.group(1)
    return None


def connect():
    if not os.path.exists(DB):
        sys.exit("找不到数据库：%s" % DB)
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    return con


def backup_db():
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = DB + ".bak-" + stamp
    shutil.copy2(DB, dst)
    for suf in ("-wal", "-shm"):
        if os.path.exists(DB + suf):
            shutil.copy2(DB + suf, dst + suf)
    return dst


def short(uid, n=8):
    return (uid or "-")[:n]


# ---------------------------------------------------------------- list

def cmd_list(args):
    con = connect()
    rows = list(con.execute(
        "select id,user_id,cwd,title,custom_title,status,transport,is_playground,"
        "deleted_at,updated_at from sessions order by user_id, updated_at"))
    me = args.uid or current_uid()

    groups = {}
    for r in rows:
        groups.setdefault(r["user_id"], []).append(r)

    print("当前登录 UID：%s" % (me or "未知"))
    print("数据库：%s" % DB)
    print()
    for uid, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        tag = "  <== 当前账号" if uid == me else ""
        alive = sum(1 for r in items if r["deleted_at"] in (None, -1))
        print("=" * 76)
        print("账号 %s  共 %d 条（未删除 %d 条）%s" % (short(uid), len(items), alive, tag))
        print("=" * 76)
        for r in items:
            state = []
            if r["deleted_at"] not in (None, -1):
                state.append("已删除")
            if r["is_playground"]:
                state.append("playground")
            if r["transport"] == "cloud":
                state.append("云端")
            flag = ("  [" + ",".join(state) + "]") if state else ""
            print("  %s  %s  %s%s" % (
                r["id"][:8], ts(r["updated_at"]),
                (r["custom_title"] or r["title"] or "(无标题)")[:38], flag))
            print("            %s" % (r["cwd"] or ""))
        print()

    if me:
        mine = len(groups.get(me, []))
        others = sum(len(v) for k, v in groups.items() if k != me)
        print("小结：当前账号 %d 条；其他账号 %d 条（这些在界面上看不到，可用 recover 迁移）" % (mine, others))

    if args.json:
        print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- locate

def find_jsonl(sid_prefix):
    hits = glob.glob(os.path.join(PROJECTS, "*", sid_prefix + "*.jsonl"))
    hits = [h for h in hits if os.sep + "subagents" + os.sep not in h]
    return hits


def cmd_locate(args):
    for p in args.id:
        hits = find_jsonl(p)
        if not hits:
            print("未找到 %s" % p)
            for h in glob.glob(os.path.join(PROJECTS, "*", p + "*.jsonl")):
                if "subagents" in h:
                    print("   （子代理日志）%s" % h)
            continue
        for h in hits:
            size = os.path.getsize(h)
            print("%s  (%.0f KB)" % (h, size / 1024))


# ---------------------------------------------------------------- recover

def cmd_recover(args):
    con = connect()
    to_uid = args.to or current_uid()
    if not to_uid:
        sys.exit("无法确定当前账号 UID，请用 --to 指定。")

    rows = list(con.execute(
        "select id,user_id,cwd,title,custom_title,transport,deleted_at,is_playground,updated_at"
        " from sessions where user_id != ? order by updated_at", (to_uid,)))

    if args.frm:
        rows = [r for r in rows if r["user_id"] == args.frm]
    if args.only:
        want = [x.strip() for x in args.only.split(",") if x.strip()]
        rows = [r for r in rows if any(r["id"].startswith(w) for w in want)]
    if args.skip:
        bad = [x.strip() for x in args.skip.split(",") if x.strip()]
        rows = [r for r in rows if not any(r["id"].startswith(b) for b in bad)]

    todo, skip = [], []
    for r in rows:
        if r["transport"] == "cloud" and not args.include_cloud:
            skip.append((r, "云端 playground/会话"))
        elif r["deleted_at"] not in (None, -1) and not args.include_deleted:
            skip.append((r, "此前已被删除"))
        else:
            todo.append(r)

    print("目标账号：%s" % to_uid)
    print("=" * 76)
    print("待迁移 %d 条：" % len(todo))
    for r in todo:
        print("  [%s] %s  <- %s" % (ts(r["updated_at"]),
                                    (r["custom_title"] or r["title"] or "")[:36],
                                    short(r["user_id"])))
        print("        %s" % (r["cwd"] or ""))
    if skip:
        print()
        print("跳过 %d 条：" % len(skip))
        for r, why in skip:
            print("  [%s] %s  <- %s" % (ts(r["updated_at"]),
                                        (r["custom_title"] or r["title"] or "")[:36], why))
    print("=" * 76)

    if not todo:
        print("没有需要迁移的记录。")
        return 0
    if not args.apply:
        print()
        print("预演模式，未做任何修改。确认后加 --apply。")
        print("提示：预算里没算上「此前已被删除」的记录，需要时加 --include-deleted。")
        return 0

    bak = backup_db()
    print()
    print("已备份 -> %s" % bak)
    ids = [r["id"] for r in todo]
    q = ",".join("?" * len(ids))
    with con:
        con.execute("update sessions set user_id=? where id in (%s)" % q, [to_uid] + ids)
        if args.include_deleted:
            con.execute("update sessions set deleted_at=NULL where id in (%s)" % q, ids)
        # 旧账号的 project_id 指向新账号无权访问的项目，清掉避免列表异常
        con.execute("update sessions set project_id=NULL "
                    "where id in (%s) and project_id is not null" % q, ids)
    left = con.execute("select count(*) from sessions where user_id=?", (to_uid,)).fetchone()[0]
    print("迁移完成：目标账号现有 %d 条会话。" % left)
    print("请**完全退出** WorkBuddy（含托盘）后重新打开，历史记录即恢复。")
    return 0


# ---------------------------------------------------------------- undelete

def cmd_undelete(args):
    con = connect()
    ids = []
    for p in args.id:
        for r in con.execute("select id from sessions where id like ?", (p + "%",)):
            ids.append(r["id"])
    if not ids:
        print("没有匹配的会话。")
        return 1
    print("将恢复 deleted_at 的会话：")
    for i in ids:
        r = con.execute("select title,custom_title,updated_at from sessions where id=?", (i,)).fetchone()
        print("  %s  [%s] %s" % (i[:8], ts(r["updated_at"]), r["custom_title"] or r["title"] or ""))
    if not args.apply:
        print("\n预演模式，未做修改。确认后加 --apply。")
        return 0
    bak = backup_db()
    print("\n已备份 -> %s" % bak)
    with con:
        con.execute("update sessions set deleted_at=NULL where id in (%s)"
                    % ",".join("?" * len(ids)), ids)
    print("已恢复，重启客户端后可见。")
    return 0


# ---------------------------------------------------------------- export

def clean_user_text(txt):
    m = re.search(r"<user_query>(.*?)</user_query>", txt, re.S)
    if m:
        return m.group(1).strip()
    t = txt
    for tag in NOISE_TAGS:
        t = re.sub(r"<%s[^>]*>.*?</%s>" % (tag, tag), "", t, flags=re.S)
        t = re.sub(r"<%s[^>]*/>" % tag, "", t)
    t = re.sub(r"<[a-z_\-]+[^>]*>", "", t)
    return t.strip()


def parts_text(content):
    """返回 (纯文本, 工具调用列表)"""
    text, tools = "", []
    if isinstance(content, str):
        return content, tools
    if not isinstance(content, list):
        return "", tools
    for p in content:
        if isinstance(p, str):
            text += p
            continue
        if not isinstance(p, dict):
            continue
        t = p.get("type")
        if t in ("input_text", "output_text", "text"):
            text += p.get("text", "")
        elif t == "tool_use":
            name = p.get("name") or p.get("toolName") or "tool"
            inp = p.get("input") or {}
            brief = ""
            for k in ("command", "file_path", "query", "pattern", "prompt", "url", "skill"):
                if isinstance(inp, dict) and inp.get(k):
                    brief = str(inp[k]).replace("\n", " ")[:110]
                    break
            tools.append((name, brief))
        elif t in ("image", "input_image"):
            text += "\n_[图片]_\n"
    return text, tools


def cmd_export(args):
    hits = find_jsonl(args.id)
    if not hits:
        sys.exit("未找到会话 %s 的正文文件。" % args.id)
    src = hits[0]
    out = args.out or os.path.join(os.getcwd(), "会话导出-%s.md" % args.id[:8])

    total = 0
    lines = []
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                o = json.loads(raw)
            except Exception:
                continue
            if o.get("type") != "message":
                continue
            role = o.get("role")
            text, tools = parts_text(o.get("content"))
            if role == "user":
                text = clean_user_text(text)
                if not text:
                    continue
                lines.append("### 用户\n\n%s\n" % text)
            elif role == "assistant":
                text = text.strip()
                if text:
                    lines.append("### 助手\n\n%s\n" % text[:args.max_chars])
                if tools and args.tools:
                    for name, brief in tools:
                        lines.append("> `%s` %s\n" % (name, brief))
            total = len(lines)

    header = (
        "# 会话导出：%s\n\n"
        "- 会话 ID：`%s`\n"
        "- 源文件：`%s`\n"
        "- 导出时间：%s\n\n---\n\n"
    ) % (args.id, args.id, src, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

    with open(out, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines))
    print("已导出 %d 段 -> %s" % (total, out))
    return 0


# ---------------------------------------------------------------- backups

def cmd_backups(args):
    baks = sorted(glob.glob(DB + ".bak-*"))
    baks = [b for b in baks if not b.endswith(("-wal", "-shm"))]
    if not baks:
        print("没有备份。")
        return 0
    for b in baks:
        print("  %s  (%.0f KB)" % (b, os.path.getsize(b) / 1024))
    if args.restore:
        target = args.restore
        cands = [b for b in baks if os.path.basename(b).endswith(target) or target in b]
        if not cands:
            sys.exit("找不到匹配的备份：%s" % target)
        src = cands[-1]
        print("\n将用 %s 覆盖 %s" % (src, DB))
        if not args.apply:
            print("预演模式，未做修改。确认后加 --apply。")
            return 0
        for f in (DB, DB + "-wal", DB + "-shm"):
            if os.path.exists(f):
                shutil.copy2(f, f + ".replaced-" + time.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(src, DB)
        for suf in ("-wal", "-shm"):
            if os.path.exists(src + suf):
                shutil.copy2(src + suf, DB + suf)
        print("已还原。建议重启客户端。")
    return 0


# ---------------------------------------------------------------- doctor

def cmd_doctor(args):
    print("数据库       : %s  %s" % (DB, "存在" if os.path.exists(DB) else "**缺失**"))
    print("当前 UID     : %s" % current_uid())
    n_proj = len([d for d in glob.glob(os.path.join(PROJECTS, "*")) if os.path.isdir(d)])
    n_jsonl = len(glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")))
    print("会话正文目录 : %s（%d 个项目目录，%d 个会话文件）" % (PROJECTS, n_proj, n_jsonl))
    con = connect()
    n_sess = con.execute("select count(*) from sessions").fetchone()[0]
    print("sessions 表  : %d 行" % n_sess)
    print("会话文件缺失 : ", end="")
    miss = []
    for r in con.execute("select id,cwd,title from sessions"):
        if not find_jsonl(r["id"]):
            miss.append(r)
    print("%d 条" % len(miss))
    for r in miss[:10]:
        print("    %s %s" % (r["id"][:8], r["cwd"] or ""))
    orphans = 0
    for h in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        if os.sep + "subagents" + os.sep in h:
            continue
        sid = os.path.basename(h)[:36]
        if not con.execute("select 1 from sessions where id=?", (sid,)).fetchone():
            orphans += 1
    print("无索引的正文 : %d 个（可正常导出，但界面上不显示）" % orphans)
    return 0


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        prog="wb_history", description="WorkBuddy 本地会话记录工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="列出全部会话，按账号分组")
    p.add_argument("--uid", help="指定当前账号 UID（默认自动探测）")
    p.add_argument("--json", action="store_true", help="额外输出原始 JSON")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("locate", help="按会话 ID 前缀找正文文件")
    p.add_argument("id", nargs="+")
    p.set_defaults(func=cmd_locate)

    p = sub.add_parser("recover", help="把其他账号的会话迁移到当前账号")
    p.add_argument("--from", dest="frm", help="源账号 UID（默认所有非当前账号）")
    p.add_argument("--to", help="目标账号 UID（默认当前登录账号）")
    p.add_argument("--only", help="只处理这些 ID 前缀，逗号分隔")
    p.add_argument("--skip", help="跳过这些 ID 前缀，逗号分隔")
    p.add_argument("--include-deleted", action="store_true", help="连同已删除的一起恢复")
    p.add_argument("--include-cloud", action="store_true", help="连云端 playground 会话一起改")
    p.add_argument("--apply", action="store_true", help="真正写库（默认只预演）")
    p.set_defaults(func=cmd_recover)

    p = sub.add_parser("undelete", help="恢复已删除的会话")
    p.add_argument("id", nargs="+")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_undelete)

    p = sub.add_parser("export", help="导出会话为 Markdown")
    p.add_argument("id", help="会话 ID 前缀")
    p.add_argument("-o", "--out", help="输出文件路径")
    p.add_argument("--max-chars", type=int, default=4000, help="单条助手回复截断长度")
    p.add_argument("--tools", action="store_true", help="附带工具调用摘要")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("backups", help="列出/还原数据库备份")
    p.add_argument("--restore", help="备份文件名（或片段）")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_backups)

    p = sub.add_parser("doctor", help="自检：索引与正文是否一致")
    p.set_defaults(func=cmd_doctor)

    args = ap.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
