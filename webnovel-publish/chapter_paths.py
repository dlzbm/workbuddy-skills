#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy 移植 shim：原仓库 scripts/chapter_paths.py 的本地替换实现。

publisher/__init__.py 的 _find_chapter_file 会 `from chapter_paths import
volume_num_for_chapter`；独立安装发布模块时该模块缺失会抛 ImportError，
故在技能根目录补一个等价实现。

原实现默认 50 章一卷：第 1—50 章为第 1 卷，第 51—100 章为第 2 卷……
本项目正文为扁平目录（正文/第0001章-标题.md，无「第N卷」子目录），
因此函数只需返回正确的卷号，查找逻辑会自动回退到正文根目录。
"""
from __future__ import annotations

CHAPTERS_PER_VOLUME = 50


def volume_num_for_chapter(chapter: int) -> int:
    """给定章号，返回其所属卷号（1 起）。"""
    try:
        n = int(chapter)
    except (TypeError, ValueError):
        return 1
    if n < 1:
        return 1
    per = CHAPTERS_PER_VOLUME if CHAPTERS_PER_VOLUME > 0 else 1
    return (n - 1) // per + 1
