#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""番茄发布向导 · 只读查询。

不执行任何写操作。一次性把「选哪本书 / 发哪几章 / 什么时候发」的候选项算好，
输出 JSON 供 Agent 生成交互选项；用户确认后再由 Agent 调用 publisher 执行发布。

用法：
    python publish_wizard.py --project-root <项目根目录> [--platform fanqie]
                             [--book-id ID]      # 覆盖项目绑定，查指定书的草稿箱

输出 JSON 字段说明：
    books                账号下所有书（id / 书名 / 字数 / 连载状态）
    bound                项目已绑定的书（取自 .webnovel/publish_config.json）
    local_max_chapter    本地 正文/ 里最新章节号
    publish_next         项目 发布/.publish_next 记录的下一批起始章号（可能为 null）
    drafts               目标书草稿箱概况（篇数 / 章号范围 / 下一批建议 / 缺失提示）
    schedule_candidates  未来几天的 20:00 定时候选（含"立即发布"）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from publisher.browser import Browser  # noqa: E402
from publisher.adapters.fanqie import FanqieAdapter  # noqa: E402

_CH_NUM = re.compile(r'第\s*(\d+)\s*章')


def chapter_num(title: str) -> int:
    m = _CH_NUM.search(title or '')
    return int(m.group(1)) if m else -1


def scan_local(root: Path) -> dict:
    """扫描本地 正文/ 目录与发布进度文件。"""
    base = root / '正文'
    nums: list[int] = []
    if base.is_dir():
        for f in base.glob('*.md'):
            n = chapter_num(f.stem)
            if n > 0:
                nums.append(n)
    nums.sort()
    progress = root / '发布' / '.publish_next'
    publish_next = None
    if progress.is_file():
        raw = progress.read_text(encoding='utf-8').strip()
        if raw.isdigit():
            publish_next = int(raw)
    return {
        'local_max_chapter': nums[-1] if nums else None,
        'local_has_files': bool(nums),
        'publish_next': publish_next,
    }


_VOL_ROW = re.compile(r'第\s*([一二三四五六七八九十百]+)\s*卷[：:]\s*([^，,约|]+)')

_CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
           '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}


def read_outline_volumes(root: Path) -> list[dict]:
    """从 大纲/总纲.md 读取各卷定义（卷名请以大纲为准，不要自拟）。

    解析形如「| **第三卷：九宗试炼，约151—260章** | ... |」的表格行。
    """
    path = root / '大纲' / '总纲.md'
    if not path.is_file():
        return []
    out: list[dict] = []
    seen: set[int] = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        m = _VOL_ROW.search(line)
        if not m:
            continue
        cn, name = m.group(1), m.group(2).strip()
        try:
            idx = _CN_NUM[cn]
        except KeyError:
            continue
        if idx in seen:
            continue
        seen.add(idx)
        out.append({'index': idx, 'full_name': f'第{cn}卷：{name}', 'topic': name})
    out.sort(key=lambda v: v['index'])
    return out


def read_binding(root: Path, platform: str) -> dict:
    cfg_path = root / '.webnovel' / 'publish_config.json'
    if not cfg_path.is_file():
        return {'book_id': '', 'book_name': '', 'config_missing': True}
    try:
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {'book_id': '', 'book_name': '', 'config_missing': True}
    b = (cfg.get('bindings') or {}).get(platform) or {}
    return {
        'book_id': str(b.get('book_id') or ''),
        'book_name': b.get('book_name') or '',
        'config_missing': False,
    }


async def main() -> None:
    ap = argparse.ArgumentParser(description='番茄发布向导（只读查询）')
    ap.add_argument('--project-root', default='.', help='小说项目根目录')
    ap.add_argument('--platform', default='fanqie')
    ap.add_argument('--book-id', default=None, help='覆盖项目绑定，查该书的草稿箱')
    args = ap.parse_args()

    root = Path(args.project_root).expanduser().resolve()
    local = scan_local(root)
    bound = read_binding(root, args.platform)

    target_id = args.book_id or bound['book_id']

    out: dict = {
        'project_root': str(root),
        'platform': args.platform,
        'bound': bound,
        'books': [],
        'drafts': None,
        'warnings': [],
    }
    out.update(local)

    if not target_id:
        out['warnings'].append('项目未绑定 book_id，也无 --book-id，无法查询草稿箱')

    browser = Browser(headless=True, platform=args.platform)
    page = await browser.start()
    adapter = FanqieAdapter()
    try:
        # ── 书单 ──
        try:
            books = await adapter.list_books(page)
        except Exception as exc:  # noqa: BLE001
            out['warnings'].append(f'查询书单失败（登录态可能已失效）: {exc}')
            books = []
        norm = []
        for b in books or []:
            bid = str(b.get('book_id') or b.get('id') or '')
            if not bid:
                continue
            norm.append({
                'book_id': bid,
                'book_name': b.get('book_name') or b.get('title') or '?',
                'word_count': b.get('word_count'),
                'creation_status': b.get('creation_status'),
                'is_bound': bid == bound.get('book_id'),
            })
        out['books'] = norm
        if target_id and norm and not any(b['book_id'] == target_id for b in norm):
            out['warnings'].append(f'绑定的 book_id {target_id} 不在书单里，可能已失效')

        # ── 草稿箱 ──
        if target_id:
            try:
                drafts = await adapter.get_all_drafts(page, target_id)
            except Exception as exc:  # noqa: BLE001
                out['warnings'].append(f'查询草稿箱失败: {exc}')
                drafts = []
            nums = sorted({chapter_num(d.get('title')) for d in drafts or []} - {-1})
            start = local['publish_next'] or (nums[0] if nums else 1)
            suggest = [n for n in range(start, start + 4)]
            missing = [n for n in suggest if nums and n not in set(nums)]
            out['drafts'] = {
                'book_id': target_id,
                'count': len(drafts or []),
                'min_chapter': nums[0] if nums else None,
                'max_chapter': nums[-1] if nums else None,
                'suggest_start': start,
                'suggest_range': f'{suggest[0]}-{suggest[-1]}' if suggest else None,
                'suggest_list': suggest,
                'missing_in_suggest': missing,
            }
            if missing:
                out['warnings'].append(
                    f'草稿箱缺少 {missing} 的草稿，需先 upload 上传再发布')

            # ── 分卷 ──
            try:
                vols = await adapter.list_volumes(page, target_id)
            except Exception as exc:  # noqa: BLE001
                out['warnings'].append(f'查询分卷失败: {exc}')
                vols = []
            norm_vols = [{
                'index': v.get('index'),
                'volume_id': str(v.get('volume_id') or ''),
                'volume_name': v.get('volume_name') or '',
                'item_count': v.get('item_count'),
            } for v in vols or []]
            out['volumes'] = norm_vols
            outline_vols = read_outline_volumes(root)
            out['outline_volumes'] = outline_vols
            if norm_vols:
                tail_map = {v['index']: v for v in outline_vols}
                nxt = tail_map.get(len(norm_vols) + 1)
                out['volume_advice'] = {
                    # 番茄按章归于卷；默认发到最后一卷（末卷为空时优先填它）
                    'suggest_target': norm_vols[-1]['volume_name'],
                    'can_create_next': bool(norm_vols[-1]['item_count']),
                    'next_outline_volume': nxt['full_name'] if nxt else None,
                }
                if not norm_vols[-1]['item_count']:
                    out['warnings'].append(
                        f"末卷「{norm_vols[-1]['volume_name']}」为空：番茄不允许在末卷为空时"
                        f"新建下一卷，需先往该卷发布至少一章")
    finally:
        await browser.close()

    # ── 定时候选 ──
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    out['schedule_candidates'] = [
        (today + timedelta(days=i)).strftime('%Y-%m-%d 20:00') for i in (0, 1, 2, 3)
    ]
    out['now'] = datetime.now().strftime('%Y-%m-%d %H:%M')

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
