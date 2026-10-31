#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""均摊排期：指定天数，按章数均摊，保证每天 >= MIN_CH 章且不超过日限。"""
import json, sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from plan_full import wc, vol_of, DAY_CAP, MONTH_CAP, USED
from project_paths import project_root

def even_plan(chs, start_day, ndays, first_n=None):
    """把 chs 均摊到 ndays 天；first_n 指定第一天章数（用于避开日限）。"""
    n = len(chs)
    if first_n:
        days = [(start_day, chs[:first_n])]
        rest = chs[first_n:]
        k = ndays - 1
        base, extra = divmod(len(rest), k)
        assert base >= 2, f"每天不足2章: base={base}"
        i = first_n
        for j in range(k):
            cnt = base + (1 if j < extra else 0)
            days.append((start_day + timedelta(days=j + 1), rest[i - first_n:i - first_n + cnt]))
            i += cnt
        return days
    base, extra = divmod(n, ndays)
    assert base >= 2, f"每天不足2章: base={base}"
    days = []
    i = 0
    for k in range(ndays):
        cnt = base + (1 if k < extra else 0)
        days.append((start_day + timedelta(days=k), chs[i:i+cnt]))
        i += cnt
    return days

def check(days):
    bad = []
    for d, cur in days:
        w = sum(wc(c) for c in cur)
        if w > DAY_CAP or len(cur) < 2:
            bad.append((d, cur, w))
    return bad

def main():
    a, b = int(sys.argv[1]), int(sys.argv[2])
    start = date.fromisoformat(sys.argv[3])
    ndays = int(sys.argv[4])
    chs = list(range(a, b + 1))
    first_n = None
    if "--first-n" in sys.argv:
        first_n = int(sys.argv[sys.argv.index("--first-n") + 1])
    days = even_plan(chs, start, ndays, first_n)
    bad = check(days)
    print(f"第{a}-{b}章 共{len(chs)}章  从{start}起 {ndays}天")
    print(f"{'日期':<12}{'章':<10}{'章数':>4}{'字数':>8}  卷")
    print("-" * 60)
    for d, cur in days:
        w = sum(wc(c) for c in cur)
        vols = sorted({vol_of(c) for c in cur})
        print(f"{d:%Y-%m-%d}  {cur[0]}-{cur[-1]:<8}{len(cur):>4}{w:>8}  {'/'.join(vols)}")
    print("-" * 60)
    tot = sum(wc(c) for c in chs)
    print(f"{'合计':<12}{'':<10}{len(chs):>4}{tot:>8}")
    by_m = {}
    for d, cur in days:
        k = d.strftime("%Y-%m")
        by_m[k] = by_m.get(k, 0) + sum(wc(c) for c in cur)
    allm = dict(USED)
    for k, v in by_m.items():
        allm[k] = allm.get(k, 0) + v
    print("\n月度（含已占用）：")
    for k in sorted(allm):
        print(f"  {k}: 本次 {by_m.get(k,0):>7} / 累计 {allm[k]:>7}  {'✅' if allm[k] <= MONTH_CAP else '❌'}")
    print(f"\n超限/不足2章的天: {[(f'{d:%m-%d}', c, w) for d, c, w in bad] or '无'}")
    if "--save" in sys.argv:
        out = [{"at": f"{d:%Y-%m-%d} 20:00", "chapters": cur} for d, cur in days]
        p = project_root() / "发布" / f"均摊排期_{a}-{b}.json"
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已存 {p}")

main()
