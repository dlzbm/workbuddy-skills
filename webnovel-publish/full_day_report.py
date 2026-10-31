#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按线上实际定时时间，统计每日/每月已排字数，检查是否超日限/月限。只读。"""
from __future__ import annotations
import asyncio, re, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from publisher.browser import Browser  # noqa: E402
import publisher as PUB  # noqa: E402

BOOK_ID = bound_book_id(ROOT)
from project_paths import project_root, bound_book_id  # noqa: E402
ROOT = project_root()
DAY_LIMIT = 9000
MONTH_LIMIT = 250000

_wc: dict[int, int] = {}
def wc(ch: int) -> int:
    if ch not in _wc:
        try:
            f = PUB._find_chapter_file(ROOT, ch)
            _wc[ch] = len(re.sub(r"\s+", "", f.read_text(encoding="utf-8").split("\n", 1)[1]))
        except Exception:
            _wc[ch] = 0
    return _wc[ch]


async def main():
    br = Browser(platform="fanqie")
    page = await br.start()
    try:
        for _ in range(4):
            try:
                await page.goto("https://fanqienovel.com/main/writer/",
                                wait_until="domcontentloaded", timeout=60_000)
                await asyncio.sleep(3)
                break
            except Exception:
                await asyncio.sleep(3)

        vols_res = await page.evaluate("""async (book_id) => {
            const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',book_id});
            const r = await fetch('https://fanqienovel.com/api/author/volume/volume_list/v1/?'+p,
                {credentials:'include'});
            return await r.json();
        }""", BOOK_ID)
        vols = {str(v["volume_id"]): v["volume_name"]
                for v in (vols_res.get("data") or {}).get("volume_list") or []}

        rows = []
        for vid in vols:
            for pi in range(0, 40):
                res = await page.evaluate("""async ([bid, vid, pi]) => {
                    const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                        book_id:bid, volume_id:vid, page_index:String(pi), page_count:'50'});
                    const r = await fetch('https://fanqienovel.com/api/author/chapter/chapter_list/v1/?'+p,
                        {credentials:'include'});
                    return await r.json();
                }""", [BOOK_ID, vid, pi])
                items = (res.get("data") or {}).get("item_list") or []
                if not items:
                    break
                for it in items:
                    m = re.search(r"第\s*(\d+)\s*章", it.get("title", ""))
                    if not m:
                        continue
                    ts = it.get("timer_time") or 0
                    at = datetime.fromtimestamp(int(ts)) if ts else None
                    rows.append({"ch": int(m.group(1)), "at": at,
                                 "vol": vols.get(str(it.get("volume_id")), "?"),
                                 "status": it.get("display_status")})
                await asyncio.sleep(0.2)

        by_day: dict[str, list] = defaultdict(list)
        by_month: dict[str, int] = defaultdict(int)
        for r in rows:
            if not r["at"]:
                continue
            k = r["at"].strftime("%Y-%m-%d %H:%M")
            by_day[k].append(r["ch"])
            by_month[r["at"].strftime("%Y-%m")] += wc(r["ch"])

        print(f"{'放出时间':<18}{'章数':>4}{'字数':>8}   章节")
        over = 0
        for k in sorted(by_day):
            chs = sorted(by_day[k])
            w = sum(wc(c) for c in chs)
            mark = "  ⚠️ 超日限" if w > DAY_LIMIT else ""
            if w > DAY_LIMIT:
                over += 1
            print(f"{k:<18}{len(chs):>4}{w:>8}   {chs[0]}-{chs[-1]}{mark}")
        print(f"\n共 {len(by_day)} 天 / {sum(len(v) for v in by_day.values())} 章定时")
        print(f"超日限(>{DAY_LIMIT})天数: {over}")
        print("\n月度合计：")
        for k in sorted(by_month):
            print(f"  {k}: {by_month[k]:>7} 字  {'✅' if by_month[k] <= MONTH_LIMIT else '❌ 超月限'}")
        pub = [r for r in rows if not r["at"]]
        print(f"\n已发布（无定时）: {len(pub)} 章")
    finally:
        await br.close()


if __name__ == "__main__":
    asyncio.run(main())
