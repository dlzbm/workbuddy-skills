#!/usr/bin/env python3
"""按目标日期分组，列出每天的章节、字数，用于定位平台「每日上限」的真实水位。只读。"""
from __future__ import annotations
import asyncio, re, html, sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from project_paths import project_root, bound_book_id  # noqa: E402
from publisher.browser import Browser  # noqa: E402
from schedule_publish import _content_of, PROJECT_ROOT  # noqa: E402

BOOK_ID = bound_book_id(PROJECT_ROOT)


async def main():
    br = Browser(headless=True, platform="fanqie")
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
        vols_res = await page.evaluate(
            """async (book_id) => {
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
                res = await page.evaluate(
                    """async ([bid, vid, pi]) => {
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
                    if m:
                        rows.append((int(m.group(1)), it.get("timer_time"),
                                     it.get("display_status"), vols.get(str(it.get("volume_id")), "?")))
                await asyncio.sleep(0.15)

        # 只关注定时中的章节（display_status=10）
        by_day: dict[str, list] = defaultdict(list)
        for n, tt, ds, vn in rows:
            if tt and ds == 10:
                d = datetime.fromtimestamp(int(tt)).strftime("%Y-%m-%d")
                by_day[d].append(n)

        print(f"{'日期':<12} {'章数':>3} {'章节':<26} {'字数':>7}")
        print("-" * 66)
        for d in sorted(by_day):
            chs = sorted(by_day[d])
            tot = 0
            for c in chs:
                try:
                    tot += len(re.sub(r"\s+", "", html.unescape(_content_of(PROJECT_ROOT, c))))
                except Exception:
                    tot += 0
            rng = f"{chs[0]}-{chs[-1]}" if len(chs) > 1 else f"{chs[0]}"
            print(f"{d:<12} {len(chs):>3} {rng:<26} {tot:>7}")

        # 找出字数最高但仍成功的几天
        print("\n按字数排序（前 12）:")
        scored = []
        for d in sorted(by_day):
            chs = sorted(by_day[d])
            tot = sum(len(re.sub(r"\s+", "", html.unescape(_content_of(PROJECT_ROOT, c)))) for c in chs)
            scored.append((tot, d, chs))
        for tot, d, chs in sorted(scored, reverse=True)[:12]:
            print(f"  {d}  {len(chs)}章  {tot} 字   {chs}")
    finally:
        await br.close()


asyncio.run(main())
