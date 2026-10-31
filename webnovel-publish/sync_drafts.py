#!/usr/bin/env python3
"""
本地正文 → 番茄草稿箱的同步工具（针对尚未发布的草稿章节）。

与 sync_chapters.py（改已发布章节，用 publish_article）不同，
草稿箱章节用 cover_article/v0/ 更新。

模式：
  backup   拉取草稿箱正文存盘（改动前的保险）
  diff     对比本地与草稿箱（只读）
  apply    把本地内容写回草稿箱
  restore  从 backup 目录回滚指定章节

用法：
  python sync_drafts.py backup  --range 53-200
  python sync_drafts.py diff    --range 53-200
  python sync_drafts.py apply   --range 53-200 [--keep-title] [--yes]
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
BACKUP_DIR = PROJECT_ROOT / "发布" / "草稿备份"
BOOK_ID = bound_book_id(PROJECT_ROOT)


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
    lines = f.read_text(encoding="utf-8").split("\n")
    title, body_start = "", 0
    for i, ln in enumerate(lines[:5]):
        if ln.startswith("# "):
            title = ln[2:].strip()
            body_start = i + 1
            break
    return {"file": f.name, "title": title,
            "content": "\n".join(lines[body_start:]).strip()}


def to_html(content: str) -> str:
    """本地 md 正文 → 平台 HTML。同 sync_chapters.to_html：
    必须走 format_for_platform 剥 markdown 标记，否则 `**加粗**` 会以
    字面星号形式上线上（实测于 2026-10-30，第 96 章）。"""
    from publisher.adapters.fanqie import _text_to_html
    from publisher.formatter import format_for_platform
    return _text_to_html(format_for_platform(content, "fanqie"))


def norm_title(t: str) -> str:
    t = re.sub(r"^第\s*\d+\s*章\s*", "", t or "").strip()
    return re.sub(r"\s+", "", t)


def plain(h: str) -> str:
    t = re.sub(r"<p>", "", h or "")
    t = re.sub(r"</p>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t).strip()


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

async def fetch_volumes(page) -> dict[str, str]:
    res = await page.evaluate(
        """async (book_id) => {
            const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',book_id});
            const r = await fetch(
                'https://fanqienovel.com/api/author/volume/volume_list/v1/?'+p,
                {credentials:'include'});
            return await r.json();
        }""", BOOK_ID)
    return {v["volume_id"]: v["volume_name"]
            for v in (res.get("data") or {}).get("volume_list") or []}


async def fetch_drafts(page) -> dict[int, dict]:
    """全分页拉草稿 → {章号: draft}。

    注意：draft_list/v1 只认 page_count=15 左右的小分页，
    传 50 会返回空列表（已发布章节的 chapter_list 才支持 50）。实测 2026-10-22。
    """
    out: dict[int, dict] = {}
    page_size = 15
    pi = 0
    while pi <= 30:
        res = await page.evaluate(
            """async ([book_id, pi, ps]) => {
                const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                    book_id, page_index: String(pi), page_count: String(ps)});
                const r = await fetch(
                    'https://fanqienovel.com/api/author/chapter/draft_list/v1/?'+p,
                    {credentials:'include'});
                return await r.json();
            }""", [BOOK_ID, pi, page_size])
        if not isinstance(res, dict) or res.get("code") != 0:
            break
        data = res.get("data") or {}
        items = data.get("draft_list") or []
        if not items:
            break
        for it in items:
            m = re.search(r"第\s*(\d+)\s*章", it.get("title", ""))
            if m:
                out[int(m.group(1))] = it
        total = data.get("total_count") or 0
        if total and len(out) >= total:
            break
        pi += 1
        await asyncio.sleep(0.2)
    return out


async def fetch_body(page, item_id: str, tries: int = 3) -> dict:
    for i in range(tries):
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
            if i == tries - 1:
                return {"code": -1, "message": f"EXC {e}"}
            await asyncio.sleep(2)
    return {"code": -1}


async def cover_draft(page, item_id: str, volume_id: str, volume_name: str,
                      title: str, content_html: str) -> dict:
    """更新草稿内容。草稿用 cover_article 即可（已发布章节才必须用 publish_article）。"""
    for attempt in range(3):
        try:
            return await page.evaluate(
                """async ([book_id, item_id, volume_id, volume_name, title, content]) => {
                    const body = new URLSearchParams({
                        aid:'2503', app_name:'muye_novel',
                        book_id, item_id, volume_id, volume_name, title, content});
                    const r = await fetch(
                        'https://fanqienovel.com/api/author/article/cover_article/v0/',
                        {method:'POST', credentials:'include', body});
                    return await r.json();
                }""", [BOOK_ID, item_id, volume_id, volume_name, title, content_html])
        except Exception as e:
            if attempt == 2:
                return {"code": -1, "message": f"EXC {e}"}
            await asyncio.sleep(2)
    return {"code": -1}


# ── 子命令 ────────────────────────────────────────────

async def cmd_backup(page, chapters: list[int]):
    drafts = await fetch_drafts(page)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ok = fail = miss = 0
    for n in chapters:
        d = drafts.get(n)
        if not d:
            print(f"[跳过] 第{n}章 草稿箱无对应草稿"); miss += 1; continue
        res = await fetch_body(page, d["item_id"])
        if res.get("code") != 0:
            print(f"[失败] 第{n}章 读取: {res.get('message')}"); fail += 1; continue
        dd = res["data"]
        (BACKUP_DIR / f"第{n:04d}章.json").write_text(
            json.dumps({"item_id": d["item_id"], "volume_id": d.get("volume_id"),
                        "list_title": d.get("title"), "title": dd.get("title", ""),
                        "content": dd.get("content", ""),
                        "word_number": d.get("word_number")},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        ok += 1
        if n % 20 == 0 or n == chapters[-1]:
            print(f"  ...已备份到第{n}章 ({ok} 篇)")
        await asyncio.sleep(0.05)
    print(f"\n备份完成: 成功 {ok} / 无草稿 {miss} / 失败 {fail} → {BACKUP_DIR}")


async def cmd_diff(page, chapters: list[int]):
    drafts = await fetch_drafts(page)
    rows, diff_list = [], []
    for n in chapters:
        loc, d = read_local(n), drafts.get(n)
        if not loc:
            rows.append((n, "缺本地文件", "", "")); diff_list.append(n); continue
        if not d:
            rows.append((n, "草稿箱无", "", "")); diff_list.append(n); continue
        res = await fetch_body(page, d["item_id"])
        if res.get("code") != 0:
            rows.append((n, "读取失败", "", "")); diff_list.append(n); continue
        dd = res["data"]
        on_plain = plain(dd.get("content", ""))
        body_same = (re.sub(r"\s+", "", on_plain)
                     == re.sub(r"\s+", "", loc["content"]))
        rows.append((n, "一致" if body_same else "有差异",
                     f"草稿{len(on_plain)}字 / 本地{len(loc['content'])}字", ""))
        if not body_same:
            diff_list.append(n)
        await asyncio.sleep(0.05)

    print(f"\n{'章':>5}  {'正文':<8} 字数对比")
    print("-" * 46)
    for r in rows:
        print(f"{r[0]:>5}  {r[1]:<8} {r[2]}")
    print("-" * 46)
    print(f"共 {len(rows)} 章，正文有差异 {len(diff_list)} 章")
    if diff_list:
        print("差异章号:", diff_list if len(diff_list) <= 40
              else f"{diff_list[:20]} ... 共{len(diff_list)}章")


async def cmd_apply(page, chapters: list[int], keep_title: bool, yes: bool):
    drafts = await fetch_drafts(page)
    vmap = await fetch_volumes(page)

    plan, miss = [], []
    for n in chapters:
        loc, d = read_local(n), drafts.get(n)
        if not loc:
            print(f"[跳过] 第{n}章 缺本地文件"); miss.append(n); continue
        if not d:
            print(f"[跳过] 第{n}章 草稿箱无对应草稿"); miss.append(n); continue
        plan.append((n, loc, d))

    print(f"\n即将写回草稿箱 {len(plan)} 章"
          f"（标题策略：{'保留线上原标题' if keep_title else '用本地标题覆盖'}）")
    if miss:
        print(f"  跳过 {len(miss)} 章: {miss[:20]}{'...' if len(miss) > 20 else ''}")
    for n, loc, d in plan[:3]:
        print(f"   第{n}章  item_id={d['item_id']}  {loc['title']}")
    print(f"   ... 共 {len(plan)} 章")
    if not yes:
        ans = input("\n确认写入草稿箱？输入 yes 继续：")
        if ans.strip().lower() != "yes":
            print("已取消，未做任何改动。"); return

    ok, fail = 0, []
    for n, loc, d in plan:
        vid = str(d.get("volume_id", ""))
        vname = vmap.get(vid, "")
        title = d.get("title", "") if keep_title else loc["title"]
        res = await cover_draft(page, d["item_id"], vid, vname,
                                title, to_html(loc["content"]))
        if res.get("code") == 0:
            ok += 1
            if ok % 30 == 0:
                print(f"  ...已写入 {ok} 篇")
        else:
            fail.append((n, res.get("message")))
            print(f"[FAIL] 第{n}章 {res.get('message')}")
        await asyncio.sleep(0.25)

    print(f"\n写入完成: 成功 {ok} / 失败 {len(fail)}")
    if fail:
        print("失败章节:", [(n, m) for n, m in fail][:20])


async def cmd_restore(page, chapters: list[int]):
    """从 backup 目录把某个/某段章节回滚到草稿箱。"""
    vmap = await fetch_volumes(page)
    ok, fail = 0, []
    for n in chapters:
        f = BACKUP_DIR / f"第{n:04d}章.json"
        if not f.exists():
            print(f"[跳过] 第{n}章 无备份文件"); fail.append(n); continue
        d = json.loads(f.read_text(encoding="utf-8"))
        vid = str(d.get("volume_id", ""))
        res = await cover_draft(page, d["item_id"], vid, vmap.get(vid, ""),
                                d.get("title", ""), d.get("content", ""))
        if res.get("code") == 0:
            ok += 1
        else:
            fail.append(n); print(f"[FAIL] 第{n}章 {res.get('message')}")
        await asyncio.sleep(0.25)
    print(f"\n回滚完成: 成功 {ok} / 失败 {len(fail)}")


async def main():
    global PROJECT_ROOT, CHAPTER_DIR, BACKUP_DIR, BOOK_ID
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["backup", "diff", "apply", "restore"])
    ap.add_argument("--range", required=True)
    ap.add_argument("--keep-title", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--project-root", default=None,
                    help="小说项目根目录（含 正文/）；缺省自动探测或读 WEBHOVEL_PROJECT_ROOT")
    args = ap.parse_args()

    if args.project_root:
        PROJECT_ROOT = Path(args.project_root).expanduser().resolve()
        CHAPTER_DIR = PROJECT_ROOT / "正文"
        BACKUP_DIR = PROJECT_ROOT / "发布" / "草稿备份"
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
        elif args.mode == "apply":
            await cmd_apply(page, chapters, args.keep_title, args.yes)
        else:
            await cmd_restore(page, chapters)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
