#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄小说登录（可靠版）。

上游 setup-auth 只判断 URL 是否像后台，未登录时也会误判成功。
本脚本改为**轮询真实 API**：直到 /api/author/homepage/book_list/v0/ 返回成功为止。

用法：
    python3 do_login.py            # 弹出浏览器，请扫码，最多等 5 分钟
    python3 do_login.py --check    # 只检查当前登录态是否有效（不开窗口，headless）

登录态保存在 ~/.webnovel-publish/browser_data/fanqie/（Playwright 持久化目录）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publisher.browser import Browser, get_user_data_dir  # noqa: E402

LOGIN_URL = "https://fanqienovel.com/main/writer/?enter_from=author_zone"
API_PATH = "/api/author/homepage/book_list/v0/"
# 该接口必带分页参数，缺了会返回 "参数有误"，导致误判为未登录
API_QUERY = "?page_count=50&page_index=0"


async def _probe_login(page) -> tuple[bool, str]:
    """调用真实书单 API 判断登录态。返回 (是否已登录, 说明)。"""
    if "fanqienovel.com" not in page.url:
        try:
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2)
        except Exception as e:
            return False, f"导航失败: {e}"

    try:
        raw = await page.evaluate(
            """async (path) => {
                const r = await fetch(path, {
                    method: 'GET',
                    credentials: 'include',
                    headers: {'Accept': 'application/json'},
                });
                return await r.text();
            }""",
            API_PATH + API_QUERY,
        )
    except Exception as e:
        return False, f"请求失败: {e}"

    try:
        body = json.loads(raw)
    except Exception:
        return False, "返回非 JSON"

    if isinstance(body, dict) and body.get("data") is not None:
        books = (body.get("data") or {}).get("book_list")
        if isinstance(books, list):
            names = [b.get("book_name", "?") for b in books]
            return True, f"已登录，书单 {len(books)} 本：{names}"
    msg = body.get("message") or body.get("msg") or ""
    return False, f"未登录（{msg or 'unknown'}）"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查登录态，不弹窗口")
    ap.add_argument("--wait", type=int, default=300, help="等待扫码秒数，默认 300")
    args = ap.parse_args()

    browser = Browser(headless=args.check, platform="fanqie")
    page = await browser.start()
    print(f"浏览器数据目录：{get_user_data_dir('fanqie')}")

    try:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)

        ok, info = await _probe_login(page)
        print(f"[状态] {info}")
        if ok:
            print("[OK] 登录态有效，无需扫码。")
            return 0

        if args.check:
            print("[FAIL] 当前未登录。请运行 `python3 do_login.py` 扫码。")
            return 1

        print(f"\n>>> 请在弹出的浏览器窗口中扫码登录，最多等待 {args.wait} 秒……\n")
        elapsed = 0
        while elapsed < args.wait:
            await asyncio.sleep(5)
            elapsed += 5
            ok, info = await _probe_login(page)
            if ok:
                print(f"[OK] {info}")
                print("[OK] 登录成功，认证状态已保存。")
                return 0
            if elapsed % 30 == 0:
                print(f"  …已等 {elapsed}s，{info}")

        print("[FAIL] 等待超时，未检测到登录成功。请重跑本脚本。")
        return 1
    finally:
        await browser.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
