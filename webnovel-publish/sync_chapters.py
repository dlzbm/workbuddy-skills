#!/usr/bin/env python3
"""
本地正文 → 番茄线上「已发布/定时」章节的同步工具。

三种模式：
  backup   拉取线上 1-N 章正文存盘（改动前的保险）
  diff    对比本地与线上，列出差异（只读，不写线上）
  apply   把本地内容写回线上（cover_article/v0/，按 item_id 精确定位）

用法：
  python sync_chapters.py backup --range 1-52
  python sync_chapters.py diff   --range 1-52
  python sync_chapters.py apply  --range 1-52 [--keep-title] [--yes]
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))

from publisher.browser import Browser  # noqa: E402

from project_paths import project_root, bound_book_id  # noqa: E402
PROJECT_ROOT = project_root()
CHAPTER_DIR = PROJECT_ROOT / "正文"
BACKUP_DIR = PROJECT_ROOT / "发布" / "线上备份"
BOOK_ID = bound_book_id(PROJECT_ROOT)

_COMMON = {"aid": "2503", "app_name": "muye_novel"}


# ── 本地文件 ──────────────────────────────────────────

def find_chapter_file(index: int) -> Path | None:
    for pat in (f"第{index:04d}章-*.md", f"第{index:03d}章-*.md", f"第{index}章-*.md"):
        hits = sorted(CHAPTER_DIR.glob(pat))
        if hits:
            return hits[0]
    return None


def read_local(index: int) -> dict | None:
    f = find_chapter_file(index)
    if not f:
        return None
    text = f.read_text(encoding="utf-8")
    lines = text.split("\n")
    title = ""
    body_start = 0
    for i, ln in enumerate(lines[:5]):
        if ln.startswith("# "):
            title = ln[2:].strip()
            body_start = i + 1
            break
    content = "\n".join(lines[body_start:]).strip()
    return {"file": f.name, "title": title, "content": content}


def to_html(content: str) -> str:
    """本地 md 正文 → 平台 HTML。

    必须走 publisher 的规范链路：format_for_platform 先剥掉 markdown 标记
    （**加粗**、# 标题等），再由 _text_to_html 按空行分段包 <p>。
    不能只做 html.escape + 拆行——那会把 `**` 当成字面字符推上线上，
    读者直接看到星号。实测于 2026-10-30：第 96 章因此带着
    `**唐书吏今日未到公署。**` 上线，改了两遍才定位到。
    """
    from publisher.adapters.fanqie import _text_to_html
    from publisher.formatter import format_for_platform
    return _text_to_html(format_for_platform(content, "fanqie"))


def norm_title(t: str) -> str:
    """归一化：去掉空格与「第N章」前缀，只比标题正文。"""
    t = re.sub(r"^第\s*\d+\s*章\s*", "", t or "").strip()
    return re.sub(r"\s+", "", t)


def platform_title(index: int, raw_title: str, filename: str = "") -> str:
    """生成本地标题的平台规范格式，与 publish-drafts 的逻辑保持一致：
    剥「第N章」前缀 → 去前导标点 → 空则回退文件名 → 「第 N 章 标题」→ 超30字截断。"""
    clean = re.sub(r"^第\s*[\d零一二三四五六七八九十百千]+\s*章\s*",
                   "", raw_title or "").strip()
    clean = clean.lstrip("：:、，,。.·—－-　 ").strip()
    if not clean and filename:
        m = re.match(r"^第\s*\d+\s*章[-—－\s　]+(.+?)\.md$", filename)
        if m:
            clean = m.group(1).strip()
    full = f"第 {index} 章 {clean}" if clean else f"第 {index} 章"
    return full[:30] if len(full) > 30 else full


def plain(html_text: str) -> str:
    text = re.sub(r"<p>", "", html_text or "")
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def parse_range(s: str) -> list[int]:
    out: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


# ── 线上交互 ──────────────────────────────────────────

async def fetch_online_index(page) -> dict[int, dict]:
    """按卷拉取全量章节 → {章号: {item_id, volume_id, title, ...}}"""
    vols = await page.evaluate(
        """async (book_id) => {
            const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',book_id});
            const r = await fetch('https://fanqienovel.com/api/author/volume/volume_list/v1/?'+p,
                {credentials:'include'});
            return await r.json();
        }""", BOOK_ID)
    vol_ids = [v["volume_id"] for v in (vols.get("data") or {}).get("volume_list") or []]

    out: dict[int, dict] = {}
    for vid in vol_ids:
        for pi in range(0, 20):
            res = await page.evaluate(
                """async ([book_id, vid, pi]) => {
                    const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                        book_id, volume_id: vid, page_index: String(pi), page_count: '50'});
                    const r = await fetch(
                        'https://fanqienovel.com/api/author/chapter/chapter_list/v1/?'+p,
                        {credentials:'include'});
                    return await r.json();
                }""", [BOOK_ID, vid, pi])
            data = res.get("data") or {}
            items = data.get("item_list") or []
            if not items:
                break
            for it in items:
                m = re.search(r"第\s*(\d+)\s*章", it.get("title", ""))
                if m:
                    out[int(m.group(1))] = it
            total = data.get("total_count") or 0
            if total and pi * 50 + len(items) >= total:
                break
            await asyncio.sleep(0.2)
    return out


async def fetch_online_body(page, item_id: str) -> dict:
    for attempt in range(4):
        try:
            return await page.evaluate(
                """async ([book_id, item_id]) => {
                    const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                        book_id, item_id, from_source:'0'});
                    const r = await fetch(
                        'https://fanqienovel.com/api/author/edit_article/v0/?'+p,
                        {credentials:'include'});
                    return await r.json();
                }""", [BOOK_ID, item_id])
        except Exception as e:
            if attempt == 3:
                return {"code": -1, "message": f"EXC {e}"}
            await asyncio.sleep(2)
    return {"code": -1}


async def push_chapter(page, item_id: str, volume_id: str, volume_name: str,
                       title: str, content_html: str, immediate: bool = True,
                       timer_time=None) -> dict:
    """写回章节正文。

    注意：cover_article/v0/ 对「已发布 / 定时」章节只返回假成功（code=0 但内容不变），
    必须用 publish_article/v0/ 才会真正落库。实测于 2026-10-21。
    """
    payload = {
        "aid": "2503", "app_name": "muye_novel",
        "book_id": BOOK_ID, "item_id": item_id,
        "volume_id": volume_id, "volume_name": volume_name,
        "title": title, "content": content_html,
        "publish_status": 1, "need_pay": 0, "device_platform": "pc",
        "speak_type": 0, "timer_chapter_preview": "[]",
        "has_chapter_ad": "false", "use_ai": 1,
        "timer_status": 0 if immediate else 1,
    }
    if not immediate:
        if not timer_time:
            return {"code": -1, "message": "保留定时但未提供 timer_time"}
        payload["timer_time"] = int(timer_time)
    for attempt in range(3):
        try:
            return await page.evaluate(
                """async (payload) => {
                    const body = new URLSearchParams(payload);
                    const r = await fetch(
                        'https://fanqienovel.com/api/author/publish_article/v0/',
                        {method:'POST', credentials:'include', body});
                    return await r.json();
                }""", payload)
        except Exception as e:
            if attempt == 2:
                return {"code": -1, "message": f"EXC {e}"}
            await asyncio.sleep(2)
    return {"code": -1}


# ── 子命令 ────────────────────────────────────────────

async def cmd_backup(page, chapters: list[int]):
    idx = await fetch_online_index(page)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for n in chapters:
        it = idx.get(n)
        if not it:
            print(f"[跳过] 第{n}章 线上不存在")
            fail += 1
            continue
        res = await fetch_online_body(page, it["item_id"])
        if res.get("code") != 0:
            print(f"[失败] 第{n}章 读取失败: {res.get('message')}")
            fail += 1
            continue
        d = res["data"]
        (BACKUP_DIR / f"第{n:04d}章.json").write_text(
            json.dumps({"item_id": it["item_id"], "volume_id": it.get("volume_id"),
                        "volume_name": it.get("volume_name", ""),
                        "list_title": it.get("title", ""),
                        "title": d.get("title", ""), "content": d.get("content", ""),
                        "word_number": it.get("word_number")},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        ok += 1
        print(f"[备份] 第{n}章 {d.get('title','')} ({len(plain(d.get('content','')))}字)")
        await asyncio.sleep(0.2)
    print(f"\n备份完成: 成功 {ok} / 失败 {fail} → {BACKUP_DIR}")


async def fetch_body_stable(page, item_id: str, tries: int = 4) -> dict:
    """读取正文，遇到刚改完的「复审中」空内容时自动等一下再读。"""
    for i in range(tries):
        res = await fetch_online_body(page, item_id)
        if res.get("code") == 0 and (res.get("data") or {}).get("content"):
            return res
        await asyncio.sleep(5)
    return res


async def cmd_diff(page, chapters: list[int]):
    idx = await fetch_online_index(page)
    rows = []
    for n in chapters:
        loc = read_local(n)
        it = idx.get(n)
        if not loc:
            rows.append((n, "缺本地文件", "", "", ""))
            continue
        if not it:
            rows.append((n, "线上不存在", "", "", ""))
            continue
        res = await fetch_body_stable(page, it["item_id"])
        if res.get("code") != 0:
            rows.append((n, "读取失败", "", "", ""))
            continue
        d = res["data"]
        on_title = d.get("title", "")
        on_plain = plain(d.get("content", ""))
        loc_plain = loc["content"]

        title_same = norm_title(on_title) == norm_title(loc["title"])
        title_fmt_same = (on_title or "").strip() == (loc["title"] or "").strip()
        body_same = re.sub(r"\s+", "", on_plain) == re.sub(r"\s+", "", loc_plain)
        rows.append((n, "一致" if (body_same and title_same) else "有差异",
                     "同" if title_same else "标题不同",
                     "同" if title_fmt_same else "格式不同",
                     f"线上{len(on_plain)}字 / 本地{len(loc_plain)}字"))
        await asyncio.sleep(0.15)

    print(f"\n{'章':>4}  {'正文':<8} {'标题':<8} {'标题格式':<8} 字数")
    print("-" * 60)
    diff_n = 0
    for r in rows:
        print(f"{r[0]:>4}  {r[1]:<8} {r[2]:<8} {r[3]:<8} {r[4]}")
        if r[1] not in ("一致",):
            diff_n += 1
    print("-" * 60)
    print(f"共 {len(rows)} 章，正文有差异 {diff_n} 章")


async def cmd_apply(page, chapters: list[int], keep_title: bool, yes: bool,
                    keep_timer: bool = False):
    idx = await fetch_online_index(page)

    plan = []
    for n in chapters:
        loc = read_local(n)
        it = idx.get(n)
        if not loc:
            print(f"[跳过] 第{n}章 缺本地文件"); continue
        if not it:
            print(f"[跳过] 第{n}章 线上不存在"); continue
        plan.append((n, loc, it))

    print(f"\n即将写回 {len(plan)} 章：{chapters[0]}—{chapters[-1]}"
          f"（标题策略：{'保留线上原标题' if keep_title else '用本地标题覆盖'}；"
          f"定时策略：{'保留原定时时间' if keep_timer else '立即发布'}）")
    for n, loc, it in plan[:5]:
        print(f"   第{n}章  item_id={it['item_id']}  {loc['title']}")
    if len(plan) > 5:
        print(f"   ... 共 {len(plan)} 章")
    if not yes:
        ans = input("\n确认写入线上？输入 yes 继续：")
        if ans.strip().lower() != "yes":
            print("已取消，未做任何改动。"); return

    # 需要卷名
    vols = await page.evaluate(
        """async (book_id) => {
            const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',book_id});
            const r = await fetch('https://fanqienovel.com/api/author/volume/volume_list/v1/?'+p,
                {credentials:'include'});
            return await r.json();
        }""", BOOK_ID)
    vmap = {v["volume_id"]: v["volume_name"]
            for v in (vols.get("data") or {}).get("volume_list") or []}

    ok = fail = 0
    for i, (n, loc, it) in enumerate(plan):
        vid = str(it.get("volume_id", ""))
        vname = vmap.get(vid, "")
        title = (it.get("title", "") if keep_title
                 else platform_title(n, loc["title"], loc.get("file", "")))
        content_html = to_html(loc["content"])
        tt = it.get("timer_time") if keep_timer else None
        if keep_timer and not tt:
            print(f"[FAIL] 第{n}章 线上无定时时间，拒绝改为立即发布")
            fail += 1
            continue
        res = await push_chapter(page, it["item_id"], vid, vname, title, content_html,
                                 immediate=not keep_timer, timer_time=tt)
        if res.get("code") == 0:
            ok += 1
            print(f"[OK]   第{n}章 {title}")
        else:
            fail += 1
            print(f"[FAIL] 第{n}章 {res.get('message')} :: {str(res)[:150]}")
        # 改后会短暂进入复审（display_status=5），给足间隔避免触发频控
        await asyncio.sleep(4 if i < len(plan) - 1 else 0)

    print(f"\n写入完成: 成功 {ok} / 失败 {fail}")


async def cmd_status(page, chapters: list[int]):
    """查看线上章节的发布状态与定时时间（只读）。"""
    import datetime
    idx = await fetch_online_index(page)
    print(f"\n{'章':>4}  {'状态':<10} {'定时时间':<18} {'字数':>6}  卷")
    print("-" * 62)
    for n in chapters:
        it = idx.get(n)
        if not it:
            print(f"{n:>4}  线上不存在")
            continue
        ds = it.get("display_status")
        status = {1: "已发布", 10: "待发布(定时)"}.get(ds, f"status={ds}")
        tt = it.get("timer_time")
        tstr = (datetime.datetime.fromtimestamp(int(tt)).strftime("%Y-%m-%d %H:%M")
                if tt else "-")
        print(f"{n:>4}  {status:<10} {tstr:<18} {it.get('word_number'):>6}  "
              f"{it.get('volume_id')}")


async def main():
    global PROJECT_ROOT, CHAPTER_DIR, BACKUP_DIR, BOOK_ID
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["backup", "diff", "apply", "status"])
    ap.add_argument("--range", default="1-52")
    ap.add_argument("--keep-title", action="store_true",
                    help="保留线上原标题，只更新正文")
    ap.add_argument("--keep-timer", action="store_true",
                    help="保留原定时时间（用于定时章节；不加则立即发布）")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--project-root", default=None,
                    help="小说项目根目录（含 正文/）；缺省自动探测或读 WEBHOVEL_PROJECT_ROOT")
    args = ap.parse_args()

    if args.project_root:
        PROJECT_ROOT = Path(args.project_root).expanduser().resolve()
        CHAPTER_DIR = PROJECT_ROOT / "正文"
        BACKUP_DIR = PROJECT_ROOT / "发布" / "线上备份"
        BOOK_ID = bound_book_id(PROJECT_ROOT)

    chapters = parse_range(args.range)
    browser = Browser(headless=True, platform="fanqie")
    page = await browser.start()
    try:
        for attempt in range(4):
            try:
                await page.goto("https://fanqienovel.com/main/writer/",
                                wait_until="domcontentloaded", timeout=60_000)
                await asyncio.sleep(3)
                break
            except Exception:
                await asyncio.sleep(3)
        if args.mode == "backup":
            await cmd_backup(page, chapters)
        elif args.mode == "diff":
            await cmd_diff(page, chapters)
        elif args.mode == "status":
            await cmd_status(page, chapters)
        else:
            await cmd_apply(page, chapters, args.keep_title, args.yes,
                            keep_timer=args.keep_timer)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
