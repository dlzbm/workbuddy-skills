#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy 移植 shim：原仓库 scripts/security_utils.py 的本地替换实现。

publisher/__init__.py 的 _read_book_meta 会 `from security_utils import
read_json_safe`；独立安装发布模块时该模块缺失会抛 ImportError，故补此实现。

read_json_safe：容忍并发写入中途（os.replace 原子替换）的瞬时损坏，
读不到就返回默认值，不让 CLI 崩掉。
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def read_json_safe(path, default=None, retries: int = 3, delay: float = 0.05):
    """安全读取 JSON 文件，失败或内容非法时返回 default。"""
    if default is None:
        default = {}
    p = Path(path)
    for attempt in range(retries):
        try:
            if not p.is_file():
                return default
            raw = p.read_text(encoding="utf-8")
            if not raw.strip():
                time.sleep(delay)
                continue
            return json.loads(raw)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            if attempt == retries - 1:
                return default
            time.sleep(delay)
    return default
