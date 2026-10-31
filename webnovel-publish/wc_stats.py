#!/usr/bin/env python3
"""统计 53—200 每章字数，并模拟不同排期口径下的每日/每月总量。只读。"""
from __future__ import annotations
import re, html, sys
from pathlib import Path
SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from schedule_publish import _content_of, PROJECT_ROOT, build_schedule, volume_of  # noqa: E402


def wc(ch: int) -> int:
    c = _content_of(PROJECT_ROOT, ch)
    return len(re.sub(r"\s+", "", html.unescape(c)))


def main():
    import argparse
    ap = argparse.ArgumentParser(description="统计每章字数并模拟排期口径下的日/月总量")
    ap.add_argument("--range", default="53-200", help="章节范围，如 53-200")
    ap.add_argument("--start", default="2026-10-22 20:00", help='模拟起始日，如 "2026-10-22 20:00"')
    args = ap.parse_args()
    a, b = (int(x) for x in args.range.split("-"))
    chs = list(range(a, b + 1))
    w = {ch: wc(ch) for ch in chs}
    total = sum(w.values())
    print(f"章节范围: {chs[0]}—{chs[-1]}  共 {len(chs)} 章")
    print(f"总字数: {total}  ({total/10000:.1f} w)")
    print(f"单章最少 {min(w.values())} / 最多 {max(w.values())} / "
          f"平均 {total/len(chs):.0f}")

    print("\n=== 当前排期（schedule_publish.build_schedule）的每日字数 ===")
    over = 0
    for d in build_schedule():
        s = sum(w[c] for c in d["chapters"])
        flag = "  ⚠ 超 1w" if s >= 10000 else ""
        if s >= 10000:
            over += 1
        print(f"  第{d['day']:>2}天 {d['at_str']}  {d['chapters'][0]:>3}-{d['chapters'][-1]:<3} "
              f"{s:>6} 字{flag}")
    print(f"  → 超 1w 的天数: {over} / {len(build_schedule())}")

    print("\n=== 若按自然月统计总量 ===")
    by_month: dict[str, int] = {}
    for d in build_schedule():
        key = d["at"].strftime("%Y-%m")
        by_month[key] = by_month.get(key, 0) + sum(w[c] for c in d["chapters"])
    for m, v in sorted(by_month.items()):
        flag = "  ⚠ 超 25w" if v > 250000 else ""
        print(f"  {m}: {v:>7} 字{flag}")

    print("\n=== 模拟：每天尽量装满但不超 10000 字 ===")
    # 贪心：按顺序把章装进当天，装不下就开下一天
    days: list[list[int]] = []
    cur: list[int] = []
    for ch in chs:
        if cur and sum(w[c] for c in cur) + w[ch] > 9999:
            days.append(cur)
            cur = []
        cur.append(ch)
    if cur:
        days.append(cur)
    from datetime import datetime, timedelta
    start = datetime.strptime(args.start, "%Y-%m-%d %H:%M")
    print(f"  需要 {len(days)} 天，从 {start.strftime('%m-%d')} 起 → "
          f"{(start + timedelta(days=len(days)-1)).strftime('%Y-%m-%d')} 收尾")
    bym: dict[str, int] = {}
    for i, dd in enumerate(days):
        at = start + timedelta(days=i)
        s = sum(w[c] for c in dd)
        bym[at.strftime('%Y-%m')] = bym.get(at.strftime('%Y-%m'), 0) + s
    for m, v in sorted(bym.items()):
        flag = "  ⚠ 超 25w" if v > 250000 else ""
        print(f"  {m}: {v:>7} 字{flag}")
    print(f"\n  前 8 天示例:")
    for i, dd in enumerate(days[:8]):
        at = start + timedelta(days=i)
        print(f"    第{i+1}天 {at.strftime('%m-%d')} {dd[0]}-{dd[-1]} "
              f"{len(dd)}章 {sum(w[c] for c in dd)} 字")


if __name__ == "__main__":
    main()
