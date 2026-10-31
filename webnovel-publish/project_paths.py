#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目根目录与 book_id 的便携解析（避免把本机路径/书号硬编码进技能）。

设计目标：换个机器、换个小说项目，脚本不用改代码就能跑。

项目根目录解析顺序（`find_project_root`）：
  1. 环境变量 ``WEBHOVEL_PROJECT_ROOT``
  2. 从 ``start``（默认当前工作目录）逐级向上，找含 ``正文/`` 子目录的目录
  3. 都找不到就退回当前目录

book_id 解析顺序（`bound_book_id`）：
  1. 环境变量 ``FANQIE_BOOK_ID``
  2. 项目 ``.webnovel/publish_config.json`` 里 ``bindings.<platform>.book_id``
  3. 都没有 → 报错并说明怎么配

因此**从小说项目根目录运行脚本**即可，无需任何配置；在别处运行可用环境变量
或各脚本的 ``--project-root`` 指定。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ENV_ROOT = "WEBHOVEL_PROJECT_ROOT"
ENV_BOOK = "FANQIE_BOOK_ID"


def find_project_root(start: Path | None = None) -> Path:
    """按优先级解析小说项目根目录（含 `正文/` 的那个目录）。"""
    env = os.environ.get(ENV_ROOT)
    if env and env.strip():
        return Path(env.strip()).expanduser().resolve()
    cur = (start or Path.cwd()).resolve()
    for cand in (cur, *cur.parents):
        if (cand / "正文").is_dir():
            return cand
    return cur


def project_root(start: Path | None = None) -> Path:
    """`find_project_root` 的别名，语义更贴近调用处。"""
    return find_project_root(start)


def bound_book_id(root: Path | str, platform: str = "fanqie") -> str:
    """取项目绑定的 book_id；取不到就带着解决办法报错。"""
    env = os.environ.get(ENV_BOOK)
    if env and env.strip():
        return env.strip()

    cfg = Path(root) / ".webnovel" / "publish_config.json"
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            binding = (data.get("bindings") or {}).get(platform) or {}
            bid = str(binding.get("book_id") or "").strip()
            if bid:
                return bid
        except (json.JSONDecodeError, OSError, AttributeError):
            pass

    raise SystemExit(
        f"未找到 book_id。请任选其一：\n"
        f"  1) 设置环境变量 {ENV_BOOK}=<book_id>\n"
        f"  2) 在 {cfg} 写入绑定：\n"
        f'     {{"bindings": {{"{platform}": {{"book_id": "<id>", "book_name": "<书名>"}}}}}}\n'
        f"  3) 先跑一次 publisher 的 upload --book <id> 让它自动绑定"
    )
