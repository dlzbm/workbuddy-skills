#!/usr/bin/env python3
"""在「每天 ≤9999 字、每月 ≤250000 字」双约束下重新排期。只读计算。

用法：
  python replan_wc.py --range 61-200 --start "2026-10-24 20:00" [--out 方案.json]
"""
from __future__ import annotations
import re, html, sys
from pathlib import Path
from datetime import datetime, timedelta
SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from project_paths import project_root  # noqa: E402
from schedule_publish import _content_of, PROJECT_ROOT, volume_of  # noqa: E402

DAY_CAP = 9999      # 每天字数上限（< 1w）
MONTH_CAP = 250000  # 每月字数上限


def wc(ch: int) -> int:
    return len(re.sub(r"\s+", "", html.unescape(_content_of(PROJECT_ROOT, ch))))


def _days_left_in_month(at: datetime) -> int:
    """含当天，本月还剩几天"""
    nxt = (at.replace(day=28) + timedelta(days=10)).replace(day=1)
    return (nxt - at).days


def main():
    import argparse
    ap = argparse.ArgumentParser(description="双约束（日限/月限）下重新排期，只读计算")
    ap.add_argument("--range", required=True, help="章节范围，如 61-200")
    ap.add_argument("--start", required=True, help='起始放出时间，如 "2026-10-24 20:00"')
    ap.add_argument("--out", default=None, help="方案输出 JSON（默认 <项目>/发布/重排方案.json）")
    args = ap.parse_args()

    a, b = (int(x) for x in args.range.split("-"))
    start_ch, end_ch = a, b
    start_day = datetime.strptime(args.start, "%Y-%m-%d %H:%M")
    w = {ch: wc(ch) for ch in range(start_ch, end_ch + 1)}
    print(f"范围 {start_ch}—{end_ch}  共 {len(w)} 章  总字数 {sum(w.values())}")

    # 逐日贪心：每天 ≤9999 字、≥2 章；某月额度按当月剩余天数摊匀，保证不超月上限
    days: list[dict] = []
    month_used: dict[str, int] = {}
    chs = list(range(start_ch, end_ch + 1))
    rest_words = sum(w[c] for c in chs)
    day_i = 0
    while chs:
        at = start_day + timedelta(days=day_i)
        key = at.strftime("%Y-%m")
        days_left_in_month = _days_left_in_month(at)
        month_budget_left = min(MONTH_CAP - month_used.get(key, 0), rest_words)
        cap = min(DAY_CAP, month_budget_left / max(1, days_left_in_month))
        cur: list[int] = []
        cur_w = 0
        while chs and len(cur) < 4 and cur_w + w[chs[0]] <= cap:
            cur.append(chs.pop(0))
            cur_w += w[cur[-1]]
        # 保底：每天至少 2 章（不超过 9999 的前提下）
        while len(cur) < 2 and chs and cur_w + w[chs[0]] <= DAY_CAP:
            cur.append(chs.pop(0))
            cur_w += w[cur[-1]]
        if not cur:
            cur.append(chs.pop(0))
            cur_w = w[cur[0]]
        days.append({"at": at, "chapters": cur, "words": cur_w})
        month_used[key] = month_used.get(key, 0) + cur_w
        rest_words -= cur_w
        day_i += 1

    print(f"\n共 {len(days)} 天：{days[0]['at'].strftime('%m-%d')} → "
          f"{days[-1]['at'].strftime('%Y-%m-%d')}（最远距起始日 "
          f"{(days[-1]['at'] - start_day).days} 天）\n")
    print(f"{'天':>3}  {'放出':<12} {'章节':<10} {'章数':>3} {'字数':>6}  卷")
    print("-" * 74)
    bym: dict[str, int] = {}
    for i, d in enumerate(days):
        vol = volume_of(d["chapters"][0])
        rng = (f"{d['chapters'][0]}" if len(d["chapters"]) == 1
               else f"{d['chapters'][0]}-{d['chapters'][-1]}")
        bym[d["at"].strftime("%Y-%m")] = bym.get(d["at"].strftime("%Y-%m"), 0) + d["words"]
        print(f"{i+1:>3}  {d['at'].strftime('%m-%d %H:%M'):<12} {rng:<10} "
              f"{len(d['chapters']):>3} {d['words']:>6}  {vol}")
    print("\n月度总量:")
    for m, v in sorted(bym.items()):
        flag = "  ⚠ 超 25w" if v > MONTH_CAP else "  ✅"
        print(f"  {m}: {v:>7} / {MONTH_CAP}{flag}")
    # 保存方案
    import json
    out = [{"at": d["at"].strftime("%Y-%m-%d %H:%M"),
            "chapters": d["chapters"], "words": d["words"]} for d in days]
    Path_ = args.out or str(project_root() / "发布" / "重排方案.json")
    open(Path_, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n方案已存: {Path_}")


if __name__ == "__main__":
    main()
