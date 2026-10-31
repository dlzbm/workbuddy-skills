#!/usr/bin/env python3
"""抽查：展示本地与线上的具体文本差异（只读）。"""
from __future__ import annotations

import asyncio
import html
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))

from publisher.browser import Browser  # noqa: E402
from sync_drafts import (BOOK_ID, CHAPTER_DIR, fetch_body, fetch_drafts,  # noqa: E402
                         find_chapter_file, plain, read_local)
from sync_chapters import fetch_online_index  # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"\s+", "", html.unescape(s or ""))


def first_diff(a: str, b: str, ctx: int = 40) -> str:
    """返回第一个差异点的上下文。"""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    if i == n and len(a) == len(b):
        return "（完全相同）"
    sa = max(0, i - ctx)
    return (f"差异位置 {i}:\n    线上: ...{a[sa:i+ctx]}...\n"
            f"    本地: ...{b[sa:i+ctx]}...")


async def main():
    targets = [int(x) for x in sys.argv[1].split(",")]
    br = Browser(platform="fanqie")
    page = await br.start()
    try:
        await page.goto("https://fanqienovel.com/main/writer/",
                        wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        drafts = await fetch_drafts(page)
        print(f"[info] 草稿箱 {len(drafts)} 篇")
        online_idx = await fetch_online_index(page)
        print(f"[info] 线上章节索引 {len(online_idx)} 章")

        for ch in targets:
            loc = read_local(ch)
            if not loc:
                print(f"\n=== 第{ch}章 === 本地文件缺失")
                continue
            it = online_idx.get(ch) or drafts.get(ch)
            if not it:
                print(f"\n=== 第{ch}章 === 线上无对应章节")
                continue
            res = await fetch_body(page, it["item_id"])
            if res.get("code") != 0:
                print(f"\n=== 第{ch}章 === 读取失败: {res.get('message')}")
                continue
            on = plain((res.get("data") or {}).get("content", ""))
            lo = loc["content"]
            same = norm(on) == norm(lo)
            print(f"\n=== 第{ch}章 {'一致' if same else '有差异'} ===")
            print(f"  标题: 线上[{it.get('title','')}] 本地[{loc['title']}]")
            print(f"  字数: 线上{len(norm(on))} / 本地{len(norm(lo))}")
            if not same:
                print("  " + first_diff(norm(on), norm(lo)))
    finally:
        await br.close()


if __name__ == "__main__":
    asyncio.run(main())
