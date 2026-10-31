#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按日期/月份统计线上已排（定时/已发布）章节，算出每月已占用额度。"""
import asyncio, re, html, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from publisher.browser import Browser

BOOK_ID = bound_book_id(PROJECT_ROOT)
from project_paths import project_root, bound_book_id  # noqa: E402
PROJECT_ROOT = project_root()
LOCAL = PROJECT_ROOT / "正文"

_wc_cache: dict[int, int] = {}
def wc(ch: int) -> int:
    if ch not in _wc_cache:
        f = sorted(LOCAL.glob(f"第{ch:04d}章-*.md"))
        _wc_cache[ch] = len(re.sub(r"\s+", "", f[0].read_text(encoding="utf-8").split("\n", 1)[1])) if f else 0
    return _wc_cache[ch]

async def main():
    br = Browser(platform="fanqie")
    page = await br.start()
    try:
        await page.goto("https://fanqienovel.com/main/writer/",
                        wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        vols = await page.evaluate("""async (bid) => {
            const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',book_id:bid});
            const r = await fetch('https://fanqienovel.com/api/author/volume/volume_list/v1/?'+p,
                {credentials:'include'});
            return await r.json();
        }""", BOOK_ID)
        vlist = (vols.get("data") or {}).get("volume_list") or []

        rows = []
        for v in vlist:
            vid = v.get("volume_id")
            for pi in range(0, 40):
                # 带重试，避免网络抖动导致空页被误判为到底
                items = []
                for attempt in range(4):
                    res = await page.evaluate("""async ([bid, vid, pi]) => {
                        const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                            book_id:bid, volume_id:vid,
                            page_index:String(pi), page_count:'50'});
                        const r = await fetch('https://fanqienovel.com/api/author/chapter/chapter_list/v1/?'+p,
                            {credentials:'include'});
                        return await r.json();
                    }""", [BOOK_ID, vid, pi])
                    items = (res.get("data") or {}).get("item_list") or []
                    if items or pi == 0:
                        break
                    await asyncio.sleep(1.5)
                if not items:
                    break
                for it in items:
                    m = re.search(r"第\s*(\d+)\s*章", it.get("title", ""))
                    if not m:
                        continue
                    ch = int(m.group(1))
                    ts = it.get("timer_time") or 0
                    at = datetime.fromtimestamp(int(ts)) if ts else None
                    rows.append({
                        "ch": ch, "vid": vid, "vname": v.get("volume_name"),
                        "status": it.get("display_status"), "at": at,
                    })
                await asyncio.sleep(0.3)
        # 按章号排序，报告
        rows.sort(key=lambda r: r["ch"])
        print(f"线上共 {len(rows)} 章\n")

        by_month: dict[str, list] = {}
        by_day: dict[str, list] = {}
        for r in rows:
            key = r["at"].strftime("%Y-%m") if r["at"] else "已发布"
            by_month.setdefault(key, []).append(r)
            if r["at"]:
                by_day.setdefault(r["at"].strftime("%Y-%m-%d"), []).append(r)

        print(f"{'月份':<10}{'章数':>6}{'字数':>10}  章节范围")
        for k in sorted(by_month):
            rs = by_month[k]
            w = sum(wc(r["ch"]) for r in rs)
            chs = sorted(r["ch"] for r in rs)
            rng = f"{chs[0]}-{chs[-1]}" if len(chs) > 1 else str(chs[0])
            print(f"{k:<10}{len(rs):>6}{w:>10}  {rng}")

        print("\n--- 最近/最远的定时日期 ---")
        sched = [r for r in rows if r["at"]]
        sched.sort(key=lambda r: r["at"])
        if sched:
            print(f"最早: {sched[0]['at']:%Y-%m-%d %H:%M}  第{sched[0]['ch']}章")
            print(f"最晚: {sched[-1]['at']:%Y-%m-%d %H:%M}  第{sched[-1]['ch']}章")
        import json
        json.dump([{**r, "at": r["at"].strftime("%Y-%m-%d %H:%M") if r["at"] else None,
                    "wc": wc(r["ch"])} for r in rows],
                  open("/tmp/online_rows.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("\n明细已存 /tmp/online_rows.json")
    finally:
        await br.stop()

asyncio.run(main())
