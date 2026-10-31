#!/usr/bin/env python3
"""把已定时发布的章节改到新的放出时间（改 timer_time，内容不变）。

用于重排：草稿箱已空，章节都在线上待发布状态，只能走 publish_article/v0/
+ timer_status=1 + 新 timer_time 来改时间。

用法：
  python retime.py --chapter 200 --at "2026-12-06 20:00"   # 试探/单章改
  python retime.py --plan 发布/重排方案_20261024.json       # 按方案批量改
"""
from __future__ import annotations
import argparse, asyncio, json, re, sys
from datetime import datetime
from pathlib import Path
SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from project_paths import project_root, bound_book_id  # noqa: E402
from publisher.browser import Browser  # noqa: E402
from publisher.adapters.fanqie import FanqieAdapter, _COMMON_FORM, _page_fetch  # noqa: E402
from schedule_publish import _title_of, _content_of, PROJECT_ROOT, volume_of  # noqa: E402

BOOK_ID = bound_book_id(PROJECT_ROOT)


async def fetch_index(page):
    """{章号: {item_id, volume_id, volume_name, timer_time, title}}"""
    vols_res = await page.evaluate(
        """async (book_id) => {
            const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',book_id});
            const r = await fetch('https://fanqienovel.com/api/author/volume/volume_list/v1/?'+p,
                {credentials:'include'});
            return await r.json();
        }""", BOOK_ID)
    vols = {str(v["volume_id"]): v["volume_name"]
            for v in (vols_res.get("data") or {}).get("volume_list") or []}
    out = {}
    for vid, vname in vols.items():
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
                    out[int(m.group(1))] = {
                        "item_id": str(it.get("item_id")),
                        "volume_id": vid,
                        "volume_name": vname,
                        "timer_time": it.get("timer_time"),
                        "display_status": it.get("display_status"),
                    }
            await asyncio.sleep(0.15)
    return out


async def retime_one(page, item_id, volume_id, volume_name, title, content, timer_time):
    form = {
        **_COMMON_FORM,
        "book_id": BOOK_ID,
        "item_id": item_id,
        "volume_id": volume_id,
        "volume_name": volume_name,
        "title": title,
        "content": content,
        "use_ai": 1,
        "timer_status": 1,
        "timer_time": int(timer_time),
        "publish_status": 1,
        "need_pay": 0,
        "device_platform": "pc",
        "speak_type": 0,
        "timer_chapter_preview": "[]",
        "has_chapter_ad": "false",
    }
    last = ""
    for attempt in range(3):
        try:
            await _page_fetch(page, "POST", "/api/author/publish_article/v0/", form=form)
            return True, ""
        except RuntimeError as e:
            last = str(e)
        except Exception as e:  # noqa: BLE001
            last = f"EXC {type(e).__name__}: {e}"
        await asyncio.sleep(3 + attempt * 4)
    return False, last


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", default=None)
    ap.add_argument("--at", default=None)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--gap", type=int, default=5)
    args = ap.parse_args()

    # 组装 {章号: 目标时间}
    targets: dict[int, str] = {}
    if args.plan:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        for d in plan:
            for ch in d["chapters"]:
                targets[int(ch)] = d["at"]
    else:
        targets[int(args.chapter)] = args.at

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
        idx = await fetch_index(page)
        print(f"线上取到 {len(idx)} 章")

        ok_n = fail_n = 0
        for ch, at_str in sorted(targets.items()):
            it = idx.get(ch)
            if not it:
                print(f"  [FAIL] 第{ch}章 线上不存在")
                fail_n += 1
                continue
            want = volume_of(ch)
            if it["volume_name"] != want:
                print(f"  [WARN] 第{ch}章 现属 {it['volume_name']}，应为 {want}，一并修正")
            timer_time = int(datetime.strptime(at_str, "%Y-%m-%d %H:%M").timestamp())
            ok, msg = await retime_one(
                page, it["item_id"], it["volume_id"], it["volume_name"],
                _title_of(PROJECT_ROOT, ch), _content_of(PROJECT_ROOT, ch), timer_time)
            if ok:
                print(f"  [OK]   第{ch}章 → {at_str}")
                ok_n += 1
            else:
                print(f"  [FAIL] 第{ch}章 {msg[:250]}")
                fail_n += 1
            await asyncio.sleep(args.gap)
        print(f"\n完成: 成功 {ok_n} / 失败 {fail_n}")
        return 0 if fail_n == 0 else 1
    finally:
        await br.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
