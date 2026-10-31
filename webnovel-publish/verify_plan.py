#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按外部排期 JSON 全量校验：卷归属 / 定时时间 / 发布状态。只读。

用法：
  python verify_plan.py 发布/均摊排期_201-260.json
  python verify_plan.py 发布/重排方案_20261024.json
  python verify_plan.py <plan.json> --body     # 额外回读正文与本地比对
"""
from __future__ import annotations
import argparse, asyncio, html, json, re, sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from publisher.browser import Browser  # noqa: E402
from publisher.formatter import format_for_platform  # noqa: E402
from publisher.adapters.fanqie import _COMMON_FORM, _page_fetch  # noqa: E402
import publisher as PUB  # noqa: E402

BOOK_ID = bound_book_id(ROOT)
from project_paths import project_root, bound_book_id  # noqa: E402
ROOT = project_root()
# 卷划分计划：示例值，请按项目 大纲/总纲.md 修改
VOLUME_PLAN = [
    (1, 60, "第一卷：逐出山门"),
    (61, 150, "第二卷：小宗门也有资格"),
    (151, 260, "第三卷：九宗试炼"),
    (261, 380, "第四卷：失踪的守阵人"),
    (381, 500, "第五卷：九州封阵"),
    (501, 600, "第六卷：自己的路"),
]
STATUS = {1: "已发布", 4: "审核中", 5: "复审中", 10: "待发布(定时)"}


def volume_of(ch: int) -> str:
    for lo, hi, name in VOLUME_PLAN:
        if lo <= ch <= hi:
            return name
    return f"?{ch}"


def local_html(idx: int) -> str:
    f = PUB._find_chapter_file(ROOT, idx)
    return format_for_platform(PUB._strip_heading_line(f.read_text(encoding="utf-8")), "fanqie")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", s or "")))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--body", action="store_true")
    args = ap.parse_args()

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    want: dict[int, str] = {}   # 章 → 期望时间 "YYYY-MM-DD HH:MM"
    want_vol: dict[int, str] = {}
    for day in plan:
        for ch in day["chapters"]:
            want[ch] = day["at"]
            want_vol[ch] = volume_of(ch)

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

        online: dict[int, dict] = {}
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
                    n = int(m.group(1))
                    ts = it.get("timer_time") or 0
                    online[n] = {
                        "status": it.get("display_status"),
                        "at": datetime.fromtimestamp(int(ts)) if ts else None,
                        "vol": vols.get(str(it.get("volume_id")), "?"),
                        "item_id": it.get("item_id"),
                        "title": it.get("title", ""),
                    }
                await asyncio.sleep(0.2)

        bad = miss = 0
        rows = []
        for ch in sorted(want):
            o = online.get(ch)
            if not o:
                print(f"  {ch:>4}  ❌ 线上不存在")
                miss += 1
                continue
            at_str = o["at"].strftime("%Y-%m-%d %H:%M") if o["at"] else "-"
            ok_t = at_str == want[ch]
            ok_v = o["vol"] == want_vol[ch]
            if not (ok_t and ok_v):
                bad += 1
                print(f"  {ch:>4}  ❌ 时间 {at_str}（应 {want[ch]}）  卷 {o['vol']}（应 {want_vol[ch]}）")
            rows.append((ch, o))

        print(f"\n计划 {len(want)} 章 / 线上 {len(rows)} 章   缺失 {miss}   不符 {bad}")

        # 按天汇总，查每日字数上限
        by_day: dict[str, list] = {}
        for day in plan:
            by_day.setdefault(day["at"], []).extend(day["chapters"])
        wc = {}
        for ch in want:
            f = PUB._find_chapter_file(ROOT, ch)
            wc[ch] = len(re.sub(r"\s+", "", f.read_text(encoding="utf-8").split("\n", 1)[1]))
        print(f"\n{'日期':<18}{'章数':>4}{'字数':>8}  章")
        over = 0
        by_month: dict[str, int] = {}
        for at in sorted(by_day):
            chs = by_day[at]
            w = sum(wc[c] for c in chs)
            mark = "  ⚠️" if w > 9000 else ""
            if w > 9000:
                over += 1
            print(f"{at:<18}{len(chs):>4}{w:>8}  {chs[0]}-{chs[-1]}{mark}")
            by_month[at[:7]] = by_month.get(at[:7], 0) + w
        print("\n月度：")
        for k in sorted(by_month):
            print(f"  {k}: {by_month[k]:>7} 字  {'✅' if by_month[k] <= 250000 else '❌超25w'}")
        print(f"\n超日限(>9000)天数: {over}")

        if args.body:
            print("\n--- 正文回读比对 ---")
            nbad = 0
            for ch, o in rows:
                res = await page.evaluate("""async ([bid, iid]) => {
                    const p = new URLSearchParams({
                        aid:'2503', app_name:'muye_novel',
                        book_id:bid, item_id:iid, from_source:'0'});
                    const r = await fetch(
                        'https://fanqienovel.com/api/author/edit_article/v0/?'+p,
                        {credentials:'include'});
                    return await r.json();
                }""", [BOOK_ID, str(o["item_id"])])
                d = res.get("data") or {}
                on = norm(d.get("content", ""))
                lo = norm(local_html(ch))
                if on != lo:
                    nbad += 1
                    print(f"  {ch:>4}  ❌ 线上 {len(on)} / 本地 {len(lo)}")
            print(f"正文不一致: {nbad} 章")
    finally:
        await br.close()


if __name__ == "__main__":
    asyncio.run(main())
