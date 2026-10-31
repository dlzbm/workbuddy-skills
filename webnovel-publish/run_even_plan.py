#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按均摊排期 JSON 执行定时发布。

与 schedule_publish.py 的区别：
  - 排期来自外部 JSON（均摊排期_*.json），而非每天固定 N 章
  - 章节可能已在「定时」状态（如探测时发出去的第201章），也能改时间
  - item_id 来源合并：草稿箱 + 已发布/定时列表

用法：
  python run_even_plan.py 发布/均摊排期_201-260.json --gap 60
  python run_even_plan.py <plan.json> --dry-run
"""
from __future__ import annotations
import argparse, asyncio, json, re, sys, time
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from publisher.browser import Browser  # noqa: E402
from publisher.formatter import format_for_platform  # noqa: E402
from publisher.adapters.fanqie import FanqieAdapter, _COMMON_FORM, _page_fetch  # noqa: E402
import publisher as PUB  # noqa: E402

from project_paths import project_root, bound_book_id  # noqa: E402
PROJECT_ROOT = project_root()
BOOK_ID = bound_book_id(PROJECT_ROOT)
USE_AI = 1   # 「是否使用AI」声明：1=是，0=否（按平台合规要求选）
# 卷划分计划：示例值，请按项目 大纲/总纲.md 修改
VOLUME_PLAN = [
    (1, 60, "第一卷：逐出山门"),
    (61, 150, "第二卷：小宗门也有资格"),
    (151, 260, "第三卷：九宗试炼"),
    (261, 380, "第四卷：失踪的守阵人"),
    (381, 500, "第五卷：九州封阵"),
    (501, 600, "第六卷：自己的路"),
]


def volume_of(ch: int) -> str:
    for lo, hi, name in VOLUME_PLAN:
        if lo <= ch <= hi:
            return name
    raise RuntimeError(f"第{ch}章不在任何卷范围内")


def title_of(idx: int) -> str:
    f = PUB._find_chapter_file(PROJECT_ROOT, idx)
    raw = f.read_text(encoding="utf-8")
    title = PUB._extract_title(raw) or f"第{idx}章"
    clean = re.sub(r"^第\s*[\d零一二三四五六七八九十百千]+\s*章\s*", "", title).strip()
    full = f"第 {idx} 章 {clean}"
    return full[:30] if len(full) > 30 else full


def content_of(idx: int) -> str:
    f = PUB._find_chapter_file(PROJECT_ROOT, idx)
    raw = f.read_text(encoding="utf-8")
    return format_for_platform(PUB._strip_heading_line(raw), "fanqie")


async def publish_one(page, item_id, volume_id, volume_name,
                      title, content, timer_time, retries=3):
    form = {
        **_COMMON_FORM, "book_id": BOOK_ID, "item_id": item_id,
        "volume_id": volume_id, "volume_name": volume_name,
        "title": title, "content": content, "use_ai": USE_AI,
        "timer_status": 1, "timer_time": int(timer_time),
        "publish_status": 1, "need_pay": 0, "device_platform": "pc",
        "speak_type": 0, "timer_chapter_preview": "[]",
        "has_chapter_ad": "false",
    }
    last = ""
    for attempt in range(retries):
        try:
            await _page_fetch(page, "POST", "/api/author/publish_article/v0/", form=form)
            return True, ""
        except RuntimeError as e:
            last = str(e)
        except Exception as e:  # noqa: BLE001
            last = f"EXC {type(e).__name__}: {e}"
        if attempt < retries - 1:
            await asyncio.sleep(3 + attempt * 4)
    return False, last


async def collect_item_ids(page) -> tuple[dict[int, str], dict[int, str]]:
    """返回 ({章号: item_id}, {章号: 来源})，来源 ∈ draft/online"""
    ids: dict[int, str] = {}
    src: dict[int, str] = {}
    # 草稿箱（page_count 只能是 ~15）
    for pi in range(0, 60):
        res = await page.evaluate("""async ([bid, pi]) => {
            const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                book_id:bid, page_index:String(pi), page_count:'15'});
            const r = await fetch('https://fanqienovel.com/api/author/chapter/draft_list/v1/?'+p,
                {credentials:'include'});
            return await r.json();
        }""", [BOOK_ID, pi])
        items = (res.get("data") or {}).get("draft_list") or []
        if not items:
            break
        for it in items:
            m = re.search(r"第\s*(\d+)\s*章", it.get("title", ""))
            if m:
                ids[int(m.group(1))] = str(it.get("item_id", ""))
                src[int(m.group(1))] = "draft"
        await asyncio.sleep(0.2)
    # 已发布/定时（按卷翻页）
    vols = await page.evaluate("""async (bid) => {
        const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',book_id:bid});
        const r = await fetch('https://fanqienovel.com/api/author/volume/volume_list/v1/?'+p,
            {credentials:'include'});
        return await r.json();
    }""", BOOK_ID)
    for v in (vols.get("data") or {}).get("volume_list") or []:
        vid = v.get("volume_id")
        for pi in range(0, 40):
            res = await page.evaluate("""async ([bid, vid, pi]) => {
                const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                    book_id:bid, volume_id:vid,
                    page_index:String(pi), page_count:'50'});
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
                    n = int(m.group(1))
                    if n not in ids:
                        ids[n] = str(it.get("item_id", ""))
                        src[n] = "online"
            await asyncio.sleep(0.2)
    return ids, src


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--gap", type=int, default=60)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    state_p = Path(args.plan).with_suffix(".state.json")
    st = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {"done": []}

    adapter = FanqieAdapter()
    browser = Browser(platform="fanqie")
    page = await browser.start()
    try:
        await adapter._ensure_writer_context(page)
        ids, src = await collect_item_ids(page)
        print(f"item_id 收集: {len(ids)} 个（草稿 {sum(1 for v in src.values() if v=='draft')} / "
              f"线上 {sum(1 for v in src.values() if v=='online')}）")

        vol_map: dict[str, tuple[str, str]] = {}
        for day in plan:
            at = datetime.strptime(day["at"], "%Y-%m-%d %H:%M")
            key = f"{day['at']}|{day['chapters'][0]}"
            if key in st["done"] and not args.force:
                print(f"\n=== {day['at']} {day['chapters']} 已完成，跳过 ===")
                continue
            print(f"\n=== {day['at']}  {day['chapters'][0]}-{day['chapters'][-1]} 章 ===")
            if args.dry_run:
                continue
            day_ok = day_fail = 0
            for ch in day["chapters"]:
                vname = volume_of(ch)
                if vname not in vol_map:
                    try:
                        vol_map[vname] = await adapter.resolve_volume(page, BOOK_ID, vname)
                    except RuntimeError:
                        print(f"  [FAIL] 第{ch}章 卷不存在: {vname}")
                        day_fail += 1
                        continue
                    print(f"  卷就绪: {vname} → {vol_map[vname][0]}")
                vid, vreal = vol_map[vname]
                item_id = ids.get(ch)
                if not item_id:
                    print(f"  [FAIL] 第{ch}章 无 item_id（草稿箱与线上都没有）")
                    day_fail += 1
                    continue
                ok, msg = await publish_one(
                    page, item_id, vid, vreal,
                    title_of(ch), content_of(ch), int(at.timestamp()))
                if ok:
                    print(f"  [OK]   第{ch}章 → {vreal}  {day['at']}"
                          f"{'  (改时间)' if src.get(ch)=='online' else ''}")
                    day_ok += 1
                else:
                    print(f"  [FAIL] 第{ch}章 {msg[:200]}")
                    day_fail += 1
                await asyncio.sleep(1.0)
            if day_fail == 0 and day_ok > 0:
                st["done"].append(key)
                state_p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
            else:
                state_p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"\n[STOP] {day['at']} 未完成（成功 {day_ok}/失败 {day_fail}），中断。")
                break
            if day is not plan[-1]:
                await asyncio.sleep(args.gap)
        print(f"\n全部完成")
    finally:
        await browser.close()


if __name__ == "__main__":
    t0 = time.time()
    asyncio.run(main())
    print(f"\n耗时 {time.time() - t0:.0f}s")
