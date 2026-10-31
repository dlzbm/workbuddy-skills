#!/usr/bin/env python3
"""
按「大纲卷划分」把草稿箱章节分批定时发布到番茄，落到对应卷。

背景（2026-10-22）：
  线上现状：第一卷 52 章（1—52），第二卷 0 章，第三卷 0 章。
  大纲/总纲.md 的卷划分：第一卷 1—60 / 第二卷 61—150 / 第三卷 151—260 /
                        第四卷 261—380 / 第五卷 381—500 / 第六卷 501—600。
  因此 53—60 → 第一卷，61—150 → 第二卷，151—200 → 第三卷。

排期：每天 20:00 放出 4 章，从 2026-10-22 起，到 200 章共 37 天。
  同一天若跨卷（第 25 天 149/150 属第二卷、151/152 属第三卷），
  会按卷拆成两次发布调用，但共用同一个放出时间。

模式：
  plan    只打印排期表（只读，不发任何请求）
  run     执行排期。默认每天之间间隔 60 秒，避免短时间大量请求被风控

用法：
  python schedule_publish.py plan
  python schedule_publish.py run --days 1            # 只跑第 1 天
  python schedule_publish.py run --day-range 2-37 --gap 60
  python schedule_publish.py run --chapter 200       # 只发某几章（探测/补发用）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timedelta
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
STATE_FILE = PROJECT_ROOT / "发布" / "定时排期_20261022.json"

# 卷划分：严格取自 大纲/总纲.md「卷划分（供规划工具读取）」，禁止自拟卷名
VOLUME_PLAN = [
    (1, 60, "第一卷：逐出山门"),
    (61, 150, "第二卷：小宗门也有资格"),
    (151, 260, "第三卷：九宗试炼"),
    (261, 380, "第四卷：失踪的守阵人"),
    (381, 500, "第五卷：九州封阵"),
    (501, 600, "第六卷：自己的路"),
]

START_CHAPTER = 53
END_CHAPTER = 200
PER_DAY = 4
FIRST_DAY = datetime(2026, 10, 22, 20, 0, 0)
USE_AI = 1  # 「是否使用AI」= 是（2026-10-18 真实抓包确认）


def volume_of(ch: int) -> str:
    for lo, hi, name in VOLUME_PLAN:
        if lo <= ch <= hi:
            return name
    raise RuntimeError(f"第{ch}章不在任何卷的范围内")


def build_schedule(start_ch: int = START_CHAPTER, end_ch: int = END_CHAPTER,
                   per_day: int = PER_DAY, first_day: datetime = FIRST_DAY):
    """返回 [ {day, date, at, groups: [(vol_name, [ch,...])]} ]"""
    chapters = list(range(start_ch, end_ch + 1))
    days = []
    day = 1
    while chapters:
        batch = chapters[:per_day]
        chapters = chapters[per_day:]
        at = first_day + timedelta(days=day - 1)
        # 同一批按卷分组
        groups: list[tuple[str, list[int]]] = []
        for ch in batch:
            v = volume_of(ch)
            if groups and groups[-1][0] == v:
                groups[-1][1].append(ch)
            else:
                groups.append((v, [ch]))
        days.append({
            "day": day,
            "at": at,
            "at_str": at.strftime("%Y-%m-%d %H:%M"),
            "chapters": batch,
            "groups": groups,
        })
        day += 1
    return days


def cmd_plan(args):
    days = build_schedule()
    print(f"排期：{START_CHAPTER}—{END_CHAPTER} 章，每天 {PER_DAY} 章，"
          f"共 {len(days)} 天，起于 {days[0]['at_str']}，止于 {days[-1]['at_str']}\n")
    print(f"{'天':>3}  {'放出时间':<17} {'章节':<14} 卷")
    print("-" * 78)
    for d in days:
        rng = f"{d['chapters'][0]}-{d['chapters'][-1]}"
        for i, (v, chs) in enumerate(d["groups"]):
            tag = f"{chs[0]}" if len(chs) == 1 else f"{chs[0]}-{chs[-1]}"
            flag = "  ⚠ 跨界天" if len(d["groups"]) > 1 and i == 0 else ""
            print(f"{d['day']:>3}  {d['at_str'] if i == 0 else '':<17} "
                  f"{tag:<14} {v}{flag}")
        _ = rng
    # 本地文件校验
    missing = [ch for day in days for ch in day["chapters"]
               if not PUB._find_chapter_file(PROJECT_ROOT, ch)]
    if missing:
        print(f"\n[WARN] 本地缺少 {len(missing)} 个章节文件: {missing[:20]}")
    else:
        print(f"\n本地文件校验通过：{START_CHAPTER}—{END_CHAPTER} 全部存在")
    print(f"\n每天之间默认间隔 {args.gap} 秒。")


def _title_of(project_root: Path, idx: int) -> str:
    """与 publisher publish-drafts 完全一致的标题生成逻辑"""
    f = PUB._find_chapter_file(project_root, idx)
    raw = f.read_text(encoding="utf-8")
    title = PUB._extract_title(raw) or f"第{idx}章"
    clean = re.sub(r"^第\s*[\d零一二三四五六七八九十百千]+\s*章\s*", "", title).strip()
    full = f"第 {idx} 章 {clean}"
    return full[:30] if len(full) > 30 else full


def _content_of(project_root: Path, idx: int) -> str:
    f = PUB._find_chapter_file(project_root, idx)
    raw = f.read_text(encoding="utf-8")
    return format_for_platform(PUB._strip_heading_line(raw), "fanqie")


async def publish_one(page, adapter, item_id, volume_id, volume_name,
                      title, content, timer_time, retries=3):
    """带重试地调用 publish_article/v0/，返回 (ok, msg)"""
    form = {
        **_COMMON_FORM,
        "book_id": BOOK_ID,
        "item_id": item_id,
        "volume_id": volume_id,
        "volume_name": volume_name,
        "title": title,
        "content": content,
        "use_ai": USE_AI,
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


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"days_done": [], "published": {}, "volume_ids": {}}


def save_state(st: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


async def cmd_run(args):
    days = build_schedule()
    if args.days:
        days = [d for d in days if d["day"] == args.days]
    elif args.day_range:
        a, b = args.day_range.split("-")
        days = [d for d in days if int(a) <= d["day"] <= int(b)]
    if not days:
        print("没有匹配的排期天。")
        return 1

    st = load_state()
    adapter = FanqieAdapter()
    browser = Browser(platform="fanqie")
    page = await browser.start()
    try:
        await adapter._ensure_writer_context(page)

        # 卷名 → (id, name)，缺失则新建
        need_vols = sorted({v for d in days for v, _ in d["groups"]})
        vol_map: dict[str, tuple[str, str]] = {}
        for vname in need_vols:
            try:
                vol_map[vname] = await adapter.resolve_volume(page, BOOK_ID, vname)
                print(f"  卷就绪: {vname} → {vol_map[vname][0]}")
            except RuntimeError:
                print(f"  卷不存在，新建: {vname}")
                data = await adapter.create_volume(page, BOOK_ID, vname)
                new_id = str(data.get("volume_id", "")) if isinstance(data, dict) else ""
                if not new_id:
                    vol_map[vname] = await adapter.resolve_volume(page, BOOK_ID, vname)
                else:
                    vol_map[vname] = (new_id, vname)
                print(f"  已新建: {vname} → {vol_map[vname][0]}")

        # 草稿 → {章号: item_id}
        drafts = await adapter.get_all_drafts(page, BOOK_ID)
        draft_by_num: dict[int, str] = {}
        for d in drafts:
            m = re.search(r"第\s*(\d+)\s*章", d.get("title", ""))
            if m:
                draft_by_num[int(m.group(1))] = str(d.get("item_id", ""))
        print(f"\n草稿箱 {len(drafts)} 篇，解析出 {len(draft_by_num)} 个章号")

        total_ok = total_fail = 0
        for di, d in enumerate(days):
            if d["day"] in st["days_done"] and not args.force:
                print(f"\n第{d['day']}天 已完成，跳过")
                continue
            timer_time = int(d["at"].timestamp())
            print(f"\n=== 第{d['day']}天 {d['at_str']}  "
                  f"{d['chapters'][0]}-{d['chapters'][-1]} 章 ===")
            if args.dry_run:
                continue
            day_ok = day_fail = 0
            for vname, chs in d["groups"]:
                vid, vreal = vol_map[vname]
                for ch in chs:
                    item_id = draft_by_num.get(ch)
                    if not item_id:
                        print(f"  [FAIL] 第{ch}章 草稿箱无对应草稿")
                        day_fail += 1
                        continue
                    ok, msg = await publish_one(
                        page, adapter, item_id, vid, vreal,
                        _title_of(PROJECT_ROOT, ch),
                        _content_of(PROJECT_ROOT, ch),
                        timer_time)
                    if ok:
                        print(f"  [OK]   第{ch}章 → {vreal}  {d['at_str']}")
                        day_ok += 1
                        st["published"][str(ch)] = {
                            "at": d["at_str"], "volume_id": vid,
                            "volume_name": vreal, "item_id": item_id,
                            "title": _title_of(PROJECT_ROOT, ch),
                        }
                    else:
                        print(f"  [FAIL] 第{ch}章 {msg[:180]}")
                        day_fail += 1
                    await asyncio.sleep(1.0)
            total_ok += day_ok
            total_fail += day_fail
            if day_fail == 0 and day_ok > 0:
                if d["day"] not in st["days_done"]:
                    st["days_done"].append(d["day"])
                save_state(st)
            else:
                save_state(st)
                print(f"\n[STOP] 第{d['day']}天 未完成（成功 {day_ok}/失败 {day_fail}），中断后续排期。")
                break
            if di < len(days) - 1 and not args.dry_run:
                await asyncio.sleep(args.gap)

        print(f"\n完成: 成功 {total_ok} / 失败 {total_fail}")
        return 0 if total_fail == 0 and total_ok > 0 else 1
    finally:
        await browser.close()


async def cmd_chapter(args):
    """单批发布指定章节（探测/补发），按大纲自动归卷"""
    chapters = []
    for part in args.chapter.split(","):
        if "-" in part:
            a, b = part.split("-")
            chapters += list(range(int(a), int(b) + 1))
        else:
            chapters.append(int(part))
    at = datetime.strptime(args.at, "%Y-%m-%d %H:%M")
    timer_time = int(at.timestamp())

    adapter = FanqieAdapter()
    browser = Browser(platform="fanqie")
    page = await browser.start()
    try:
        await adapter._ensure_writer_context(page)
        drafts = await adapter.get_all_drafts(page, BOOK_ID)
        draft_by_num = {}
        for d in drafts:
            m = re.search(r"第\s*(\d+)\s*章", d.get("title", ""))
            if m:
                draft_by_num[int(m.group(1))] = str(d.get("item_id", ""))
        ok_n = fail_n = 0
        for ch in chapters:
            vname = volume_of(ch)
            try:
                vid, vreal = await adapter.resolve_volume(page, BOOK_ID, vname)
            except RuntimeError as e:
                print(f"  [FAIL] 第{ch}章 {e}")
                fail_n += 1
                continue
            item_id = draft_by_num.get(ch)
            if not item_id:
                print(f"  [FAIL] 第{ch}章 无草稿")
                fail_n += 1
                continue
            ok, msg = await publish_one(page, adapter, item_id, vid, vreal,
                                        _title_of(PROJECT_ROOT, ch),
                                        _content_of(PROJECT_ROOT, ch), timer_time)
            if ok:
                print(f"  [OK]   第{ch}章 → {vreal}  {at.strftime('%Y-%m-%d %H:%M')}")
                ok_n += 1
            else:
                print(f"  [FAIL] 第{ch}章 {msg[:300]}")
                fail_n += 1
            await asyncio.sleep(1.0)
        print(f"\n完成: 成功 {ok_n} / 失败 {fail_n}")
        return 0 if fail_n == 0 else 1
    finally:
        await browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["plan", "run", "chapter"])
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--day-range", default=None)
    ap.add_argument("--chapter", default=None)
    ap.add_argument("--at", default="2026-10-22 20:00")
    ap.add_argument("--gap", type=int, default=60)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.mode == "plan":
        cmd_plan(args)
        return 0
    if args.mode == "chapter":
        return asyncio.run(cmd_chapter(args))
    return asyncio.run(cmd_run(args))


if __name__ == "__main__":
    t0 = time.time()
    SKILL_DIR = Path(__file__).resolve().parent
    sys.path.insert(0, str(SKILL_DIR))
    code = main()
    print(f"\n耗时 {time.time() - t0:.0f}s")
    sys.exit(code)
