#!/usr/bin/env python3
"""全量校验：53—200 章的卷归属 / 定时时间 / 发布状态是否符合排期表。只读。"""
from __future__ import annotations
import asyncio, re, sys
from datetime import datetime
from pathlib import Path
SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from publisher.browser import Browser  # noqa: E402
from schedule_publish import build_schedule, volume_of, BOOK_ID  # noqa: E402

from project_paths import project_root, bound_book_id  # noqa: E402
ROOT = project_root()


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

        online: dict[int, dict] = {}
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
                        online[int(m.group(1))] = it
                await asyncio.sleep(0.15)

        # 草稿箱剩余
        drafts_res = await page.evaluate(
            """async (book_id) => {
                const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                    book_id, page_index:'0', page_count:'15'});
                const r = await fetch('https://fanqienovel.com/api/author/chapter/draft_list/v1/?'+p,
                    {credentials:'include'});
                return await r.json();
            }""", BOOK_ID)
        draft_total = (drafts_res.get("data") or {}).get("total_count")

        # 期望：{章号: (放出时间str, 卷名)}
        expect = {}
        for d in build_schedule():
            for vname, chs in d["groups"]:
                for ch in chs:
                    expect[ch] = (d["at_str"], vname)

        bad = 0
        miss = 0
        print(f"{'章':>4}  {'状态':<10} {'定时时间':<17} {'卷':<22} 检查")
        print("-" * 78)
        for n in range(53, 201):
            it = online.get(n)
            if not it:
                print(f"{n:>4}  线上不存在")
                miss += 1
                continue
            ds = it.get("display_status")
            status = {1: "已发布", 10: "待发布(定时)"}.get(ds, f"status={ds}")
            tt = it.get("timer_time")
            tstr = (datetime.fromtimestamp(int(tt)).strftime("%Y-%m-%d %H:%M")
                    if tt else "-")
            vname = vols.get(str(it.get("volume_id")), "?")
            exp_t, exp_v = expect[n]
            errs = []
            if vname != exp_v:
                errs.append(f"卷应为{exp_v}")
            if tstr != exp_t and ds != 1:
                errs.append(f"时间应为{exp_t}")
            if tt and ds not in (10,):
                errs.append(f"状态异常({status})")
            if errs:
                bad += 1
            print(f"{n:>4}  {status:<10} {tstr:<17} {vname:<22} "
                  f"{'❌ ' + '; '.join(errs) if errs else '✅'}")

        print(f"\n草稿箱剩余: {draft_total} 篇")
        print(f"缺失: {miss} 章   不符: {bad} 章")
        return 0 if (miss == 0 and bad == 0) else 1
    finally:
        await br.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
