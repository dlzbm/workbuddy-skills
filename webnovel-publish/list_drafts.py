#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查看番茄草稿箱现有草稿（只读，不改动任何东西）。

用法：
    python3 list_drafts.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))

from project_paths import project_root  # noqa: E402

# 不传 --project-root 时自动探测（见 project_paths.py）
PROJECT_ROOT = None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=PROJECT_ROOT,
                    help="小说项目根目录（含 正文/）；默认自动探测")
    ap.add_argument("--book", default=None)
    args = ap.parse_args()

    from publisher.browser import Browser
    from publisher.adapters import get_adapter
    from publisher.config import resolve_book_id

    root = (Path(args.project_root).expanduser().resolve()
            if args.project_root else project_root())
    book_id = resolve_book_id(root, "fanqie", args.book)
    print(f"book_id: {book_id}")

    adapter = get_adapter("fanqie")
    browser = Browser(platform="fanqie")
    page = await browser.start()
    try:
        drafts = await adapter.get_all_drafts(page, book_id)
        print(f"草稿箱共 {len(drafts)} 篇：")
        if drafts:
            for d in drafts:
                print(
                    f"  item_id={d.get('item_id', '?')}  "
                    f"title={d.get('title', '?')!r}  "
                    f"modify={d.get('modify_time', d.get('create_time', '?'))}"
                )
        else:
            print("  （空——可以放心开始自动发布）")
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
