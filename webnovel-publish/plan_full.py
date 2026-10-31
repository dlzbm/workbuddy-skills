#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按「每日字数上限 + 每月字数上限 + 无空档 + 每天≥N章」生成全书分批排期。

约束（平台实测）：
  - 每日提交字数上限约 9000（实测 9079 可过，12645 被拒）
  - 每月排定字数上限 250000
  - 定时最远可排 ≥ 88 天（2026-10-24 实测排到 2027-01-20 成功）
"""
import json, re, sys
from datetime import date, timedelta
from pathlib import Path

from project_paths import project_root, bound_book_id  # noqa: E402
ROOT = project_root()
LOCAL = ROOT / "正文"
DAY_CAP = 8800          # 每日上限（留余量）
MONTH_CAP = 250000      # 每月上限
MIN_CH = 2              # 每天最少章数

# 大纲卷划分（取自项目 大纲/总纲.md）。
# ⚠️ 下面是示例值，请按你项目的实际卷划分修改；USED 为线上已占用额度，
#    可用 month_report.py 实测后填入（不知道就留空 dict）。
VOL_RANGES = [
    ("第一卷：逐出山门",       1,   60),
    ("第二卷：小宗门也有资格", 61,  150),
    ("第三卷：九宗试炼",       151, 260),
    ("第四卷：失踪的守阵人",   261, 380),
    ("第五卷：九州封阵",       381, 500),
    ("第六卷：自己的路",       501, 600),
]

def vol_of(ch: int):
    for name, a, b in VOL_RANGES:
        if a <= ch <= b:
            return name
    return None

_wc: dict[int, int] = {}
def wc(ch: int) -> int:
    if ch not in _wc:
        f = sorted(LOCAL.glob(f"第{ch:04d}章-*.md"))
        _wc[ch] = len(re.sub(r"\s+", "", f[0].read_text(encoding="utf-8").split("\n", 1)[1])) if f else 0
    return _wc[ch]

# 线上已占用额度（month_report 实测）
USED = {
    "2026-10": 55213, "2026-11": 225839, "2026-12": 88202, "2027-01": 3364,
}

def build(start_ch: int, end_ch: int, start_day: date, max_day: date):
    """从 start_ch 顺序装天，返回 [(date, [ch,...])]"""
    days: list[tuple[date, list[int]]] = []
    used = dict(USED)
    chs = list(range(start_ch, end_ch + 1))
    d = start_day
    while chs and d <= max_day:
        key = d.strftime("%Y-%m")
        room_m = MONTH_CAP - used.get(key, 0)
        cap = min(DAY_CAP, room_m)
        cur: list[int] = []
        cur_w = 0
        while chs and cur_w + wc(chs[0]) <= cap:
            cur.append(chs.pop(0)); cur_w += wc(cur[-1])
        # 每天最少 MIN_CH 章：装不满就硬塞（单章超 cap 的极端情况除外）
        while len(cur) < MIN_CH and chs:
            nxt = chs[0]
            if cur_w + wc(nxt) > cap and cur:
                break
            cur.append(chs.pop(0)); cur_w += wc(cur[-1])
            if not chs:
                break
        if not cur:
            break
        days.append((d, cur))
        used[key] = used.get(key, 0) + cur_w
        d += timedelta(days=1)
    return days, chs

def show(days, chs_left):
    print(f"\n{'日期':<12}{'章':<8}{'章数':>4}{'字数':>8}  卷")
    print("-" * 66)
    by_month: dict[str, int] = {}
    over = 0
    for d, cur in days:
        w = sum(wc(c) for c in cur)
        vols = sorted({vol_of(c) for c in cur})
        flag = ""
        if w > DAY_CAP:
            flag = f"  ⚠️超日限"; over += 1
        print(f"{d:%Y-%m-%d}  {cur[0]}-{cur[-1] if len(cur)>1 else cur[0]:<8}"
              f"{len(cur):>4}{w:>8}  {'/'.join(vols)}{flag}")
        by_month[d.strftime("%Y-%m")] = by_month.get(d.strftime("%Y-%m"), 0) + w
    print("-" * 66)
    print(f"{'合计':<12}{'':<8}{sum(len(c) for _,c in days):>4}"
          f"{sum(sum(wc(c) for c in cur) for _,cur in days):>8}")
    print("\n月度汇总（含已占用）：")
    allm = dict(USED)
    for k, v in by_month.items():
        allm[k] = allm.get(k, 0) + v
    for k in sorted(allm):
        new = by_month.get(k, 0)
        mark = "✅" if allm[k] <= MONTH_CAP else "❌超月限"
        print(f"  {k}: 本次 {new:>7} / 累计 {allm[k]:>7}  {mark}")
    print(f"\n超日限天数: {over}")
    print(f"未排完剩余: {len(chs_left)} 章" + (f"（第{chs_left[0]}-{chs_left[-1]}章）" if chs_left else ""))

def main():
    start_ch = int(sys.argv[1]) if len(sys.argv) > 1 else 201
    end_ch = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    start_day = date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else date(2026, 12, 16)
    max_day = date.fromisoformat(sys.argv[4]) if len(sys.argv) > 4 else date(2027, 1, 20)
    days, left = build(start_ch, end_ch, start_day, max_day)
    print(f"排期范围: 第{start_ch}-{end_ch}章  从 {start_day} 起，最远 {max_day}")
    show(days, left)
    if "--save" in sys.argv:
        out = [{"at": f"{d:%Y-%m-%d} 20:00", "chapters": cur} for d, cur in days]
        p = ROOT / "发布" / f"分批排期_{start_ch}-{end_ch}.json"
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n已存 {p}")

if __name__ == "__main__":
    main()
