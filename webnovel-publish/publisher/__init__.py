# .opencode/scripts/publisher/__init__.py
"""小说自动发布 — CLI 入口。

用法:
  python publisher/__init__.py --project-root <path> setup-auth --platform fanqie
  python publisher/__init__.py --project-root <path> list-books --platform fanqie
  python publisher/__init__.py --project-root <path> create-book --platform fanqie
  python publisher/__init__.py --project-root <path> upload --platform fanqie --book <id>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

# subprocess 运行时 scripts/ 不在 Python path 中，确保绝对导入可用
_scripts_root = Path(__file__).resolve().parent.parent
if str(_scripts_root) not in sys.path:
    sys.path.insert(0, str(_scripts_root))

from publisher.adapters import get_adapter as _get_adapter_impl


def _get_adapter(platform: str):
    try:
        return _get_adapter_impl(platform)
    except ValueError as e:
        from publisher.adapters import list_platforms
        print(f"{e}")
        print(f"可用平台: {', '.join(list_platforms())}")
        sys.exit(1)


async def _cmd_list_volumes(args: argparse.Namespace):
    """列出某本书的全部分卷（含每卷章节数）。"""
    from publisher.browser import Browser
    from publisher.config import resolve_book_id

    project_root = Path(args.project_root).expanduser().resolve()
    book_id = resolve_book_id(project_root, args.platform, getattr(args, 'book', None))
    adapter = _get_adapter(args.platform)
    browser = Browser(platform=args.platform)
    page = await browser.start()
    try:
        vols = await adapter.list_volumes(page, book_id)
        print(f'book_id: {book_id}')
        print(f'共 {len(vols)} 个卷：')
        for v in vols:
            print(f"  [卷{v.get('index')}] {v.get('volume_name')}  "
                  f"id={v.get('volume_id')}  章数={v.get('item_count')}")
        tail = vols[-1] if vols else None
        if tail and not tail.get('item_count'):
            print(f"\n  ⚠️ 最后一卷「{tail.get('volume_name')}」为空：番茄不允许在末卷为空时"
                  f"继续建新卷，需先往该卷发至少一章。")
    finally:
        await browser.close()


async def _cmd_create_volume(args: argparse.Namespace):
    """新建分卷。卷名请以「大纲/总纲.md」中的定义为准。"""
    from publisher.browser import Browser
    from publisher.config import resolve_book_id

    project_root = Path(args.project_root).expanduser().resolve()
    book_id = resolve_book_id(project_root, args.platform, getattr(args, 'book', None))
    adapter = _get_adapter(args.platform)
    browser = Browser(platform=args.platform)
    page = await browser.start()
    try:
        before = await adapter.list_volumes(page, book_id)
        tail = before[-1] if before else None
        if tail and not tail.get('item_count'):
            print(f"[ERROR] 末卷「{tail.get('volume_name')}」章数为 0。"
                  f"番茄限制：末卷为空时不能再建新卷。请先往该卷发布至少一章。")
            sys.exit(1)

        if not getattr(args, 'yes', False):
            resp = _safe_input(f'新建卷「{args.name}」到书籍 {book_id}？(Y/n): ', default='y')
            if resp.lower() in ('n', 'no'):
                print('已取消。')
                sys.exit(1)

        await adapter.create_volume(page, book_id, args.name)

        after = await adapter.list_volumes(page, book_id)
        if len(after) > len(before):
            newv = after[-1]
            print(f'[OK] 已新建: {newv.get("volume_name")}  volume_id={newv.get("volume_id")}')
        else:
            print(f'[WARN] 接口已调用但卷数未增加（{len(before)} -> {len(after)}），请到后台核验。')
            sys.exit(1)
    finally:
        await browser.close()


async def _cmd_setup_auth(args: argparse.Namespace):
    from publisher.browser import Browser
    adapter = _get_adapter(args.platform)
    browser = Browser(headless=False, platform=args.platform)
    page = await browser.start()
    try:
        ok = await adapter.setup_auth(page)
        if ok:
            print(f"[OK] {adapter.display_name} 登录成功，认证状态已自动保存")
        else:
            print(f"[FAIL] {adapter.display_name} 登录超时")
            sys.exit(1)
    finally:
        await browser.close()


async def _cmd_list_books(args: argparse.Namespace):
    from publisher.browser import Browser
    adapter = _get_adapter(args.platform)
    browser = Browser(platform=args.platform)
    page = await browser.start()
    try:
        books = await adapter.list_books(page)
        if not books:
            print("未找到书籍")
        else:
            for i, book in enumerate(books, 1):
                bid = book.get("book_id", "") or book.get("id", "")
                name = book.get("book_name", book.get("title", "未知"))
                print(f"  {i}. {name}  (book_id: {bid})")
    finally:
        await browser.close()


async def _cmd_create_book(args: argparse.Namespace):
    from publisher.browser import Browser
    from publisher.base import BookMeta
    from publisher.config import save_publish_config, load_publish_config
    adapter = _get_adapter(args.platform)
    project_root = Path(args.project_root).expanduser().resolve()
    meta = _read_book_meta(project_root)

    # 简介：自动生成 or 用户输入 or 跳过
    abstract = _build_abstract_from_project(project_root)
    if args.abstract:
        abstract = args.abstract
    elif not args.yes:
        print(f"\n自动生成简介:\n  {abstract}\n")
        choice = _safe_input("使用自动简介？[Y=使用 / 输入新简介 / N=跳过]: ", default="y")
        if choice.lower() == 'n':
            abstract = ""
        elif choice and choice.lower() != 'y':
            abstract = choice
    print(f"书名: {meta.title}")
    print(f"题材: {meta.genre}")
    print(f"简介: {abstract or '(跳过)'}")
    if not args.yes:
        resp = _safe_input("\n确认创建？(Y/n): ", default="y")
        if resp.lower() in ('n', 'no'):
            print("已取消。")
            return

    browser = Browser(platform=args.platform)
    page = await browser.start()
    try:
        book_id = await adapter.create_book(page, meta)
        if book_id:
            print(f"[OK] 书籍创建成功！book_id: {book_id}")
            # 绑定到项目
            cfg = load_publish_config(project_root)
            cfg.setdefault("bindings", {})[args.platform] = {
                "book_id": book_id, "book_name": meta.title,
            }
            save_publish_config(project_root, cfg)
            print(f"  已绑定到项目: {project_root}")
        else:
            print("[FAIL] 创建失败，请手动检查")
            sys.exit(1)
    finally:
        await browser.close()


def _build_abstract_from_project(project_root: Path) -> str:
    """从项目元数据自动生成简介（50+ 字）。"""
    state_path = project_root / ".webnovel" / "state.json"
    pi = {}
    if state_path.is_file():
        # P2 修复：直读改走 read_json_safe（并发 os.replace 中途容错 + 失败降级 {}）
        try:
            from security_utils import read_json_safe
        except ImportError:  # pragma: no cover
            from scripts.security_utils import read_json_safe
        state = read_json_safe(state_path, default={})
        pi = state.get("project_info", {}) if isinstance(state, dict) else {}
    parts = []
    selling = pi.get("core_selling_points", "")
    if selling:
        parts.append(selling)
    world = pi.get("world_scale", "")
    gf = pi.get("golden_finger_name", "")
    if gf and world:
        parts.append(f"{world}背景，{gf}为刃")
    return "。".join(parts) if parts else ""


async def _cmd_upload(args: argparse.Namespace):
    from publisher.browser import Browser
    from publisher.base import Chapter
    from publisher.config import PublishConfig, load_upload_log, save_upload_log, resolve_book_id
    from publisher.formatter import format_for_platform

    project_root = Path(args.project_root).expanduser().resolve()
    book_id = resolve_book_id(project_root, args.platform, getattr(args, 'book', None))
    # 首次上传时自动持久化绑定
    if getattr(args, 'book', None):
        from publisher.config import load_publish_config, save_publish_config
        cfg = load_publish_config(project_root)
        if str(args.platform) not in cfg.get("bindings", {}):
            cfg.setdefault("bindings", {})[args.platform] = {"book_id": book_id}
            save_publish_config(project_root, cfg)

    adapter = _get_adapter(args.platform)
    adapter.set_mode(args.mode)
    cfg = PublishConfig(mode=args.mode)
    project_name = project_root.name
    uploaded = load_upload_log(args.platform, book_id, project_name)

    # 交叉校验：防止 book_id 误用
    from publisher.config import get_log_path
    log_path = get_log_path(args.platform, book_id, project_name)
    if log_path.is_file():
        try:
            log_data = json.loads(log_path.read_text(encoding="utf-8"))
            logged_book_id = log_data.get("book_id", "")
            if logged_book_id and logged_book_id != book_id:
                logged_name = log_data.get("book_name", "未知")
                print(f"⚠️ 警告: 上传日志中的 book_id ({logged_book_id}, {logged_name}) 与当前 book_id ({book_id}) 不一致！")
                print("可能原因: 误用了另一本书的 book_id。")
                if getattr(args, 'yes', False):
                    print("--yes 已指定，跳过确认继续上传。")
                else:
                    resp = _safe_input("确认继续上传？(y/N): ", default="n")
                    if resp.lower() != "y":
                        print("已取消。")
                        sys.exit(1)
        except (json.JSONDecodeError, KeyError):
            pass

    book_meta = _read_book_meta(project_root)
    book_name = book_meta.title if book_meta else ""
    chapter_indices = _parse_range(args.range, project_root)
    to_upload = [i for i in chapter_indices if i not in uploaded]
    if not to_upload:
        print("所有章节已上传。")
        return

    # 上传确认摘要
    print(
        f"目标书籍: {book_name or '?'} (book_id: {book_id})\n"
        f"待上传: {len(to_upload)} 章 "
        f"(共 {len(chapter_indices)} 章, {len(uploaded)} 章已传)\n"
        f"模式: {args.mode}"
    )
    if not getattr(args, 'yes', False):
        resp = _safe_input("继续？(Y/n): ", default="y")
        if resp.lower() in ('n', 'no'):
            print("已取消。")
            sys.exit(1)

    browser = Browser(headless=cfg.headless, platform=args.platform)
    page = await browser.start()
    success_count = 0
    fail_count = 0

    try:
        for idx in to_upload:
            chapter_file = _find_chapter_file(project_root, idx)
            if not chapter_file:
                print(f"  [WARN] 第{idx}章文件未找到，跳过")
                fail_count += 1
                continue

            raw_md = chapter_file.read_text(encoding="utf-8")
            title = _extract_title(raw_md) or f"第{idx}章"
            # 剔除首行标题（平台 API 单独设标题，正文不需重复）
            raw_md = _strip_heading_line(raw_md)
            content = format_for_platform(raw_md, args.platform)
            chapter = Chapter(index=idx, title=title, content=content)

            try:
                result = await adapter.upload_chapter(page, book_id, chapter)
            except RuntimeError as e:
                fail_count += 1
                print(f"  [FAIL] 第{idx}章 {e}")
                await asyncio.sleep(cfg.chapter_gap)
                continue
            if result.success:
                uploaded.add(idx)
                save_upload_log(args.platform, book_id, uploaded, book_name=book_name, project_name=project_name)
                success_count += 1
                print(f"  [OK] 第{idx}章 {result.message}")
            else:
                fail_count += 1
                print(f"  [FAIL] 第{idx}章 {result.message}")

            await asyncio.sleep(cfg.chapter_gap)
    finally:
        await browser.close()

    print(f"\n上传完成: 成功 {success_count}, 失败 {fail_count}")
    if fail_count > 0:
        print("[ERROR] 存在上传失败的章节，返回非 0 退出码，调用方请勿推进进度。")
        sys.exit(1)


# ── 草稿管理命令 ───────────────────────────────────────────────────────────────
# 来源：合并自根目录的 fanqie_publish.py, clean_drafts.py, clear_drafts.py
# 功能：清理重复草稿、清空草稿箱、删除全部草稿、发布草稿

async def _cmd_clean_drafts(args: argparse.Namespace):
    """清理草稿箱中的重复章节（同章节号保留最新修改时间的）。
    
    适用场景：多次上传同一章导致草稿箱有重复，只想保留最新版本。
    """
    from collections import defaultdict
    from publisher.browser import Browser
    from publisher.config import resolve_book_id
    
    project_root = Path(args.project_root).expanduser().resolve()
    book_id = resolve_book_id(project_root, args.platform, getattr(args, 'book', None))
    
    adapter = _get_adapter(args.platform)
    browser = Browser(platform=args.platform)
    page = await browser.start()
    
    try:
        drafts = await adapter.get_all_drafts(page, book_id)
        if not drafts:
            print('草稿箱为空。')
            return
        
        # 按章节号分组
        groups = defaultdict(list)
        for d in drafts:
            title = d.get('title', '')
            m = re.search(r'第\s*(\d+)\s*章', title)
            if not m:
                continue  # 序章、楔子、番外等不参与去重
            idx = int(m.group(1))
            groups[idx].append(d)

        # 找重复
        to_delete = []
        for idx, items in sorted(groups.items()):
            if len(items) <= 1:
                continue
            sorted_items = sorted(items, key=lambda x: int(str(x.get('modify_time', 0)) or 0), reverse=True)
            keep = sorted_items[0]
            delete = sorted_items[1:]
            print(f'第{idx}章 ({len(items)}篇): 保留 {keep["item_id"]} ({keep["title"]})')
            for d in delete:
                print(f'  将删除 {d["item_id"]} ({d["title"]})')
                to_delete.append(d)
        
        if not to_delete:
            print('没有重复草稿，无需清理。')
            return
        
        print(f'\n共需删除 {len(to_delete)} 篇重复草稿')
        if getattr(args, 'dry_run', False):
            print('[DRY-RUN] 不执行实际删除')
            return
        
        if not getattr(args, 'yes', False):
            resp = _safe_input('确认删除？(y/N): ', default='n')
            if resp.lower() != 'y':
                print('已取消。')
                return
        
        success = fail = 0
        for d in to_delete:
            item_id = str(d.get('item_id', ''))
            title = d.get('title', '')
            if await adapter.delete_draft(page, book_id, item_id):
                print(f'  [DEL] {title} ({item_id})')
                success += 1
            else:
                print(f'  [FAIL] {title}')
                fail += 1
            await asyncio.sleep(0.8)
        
        print(f'\n清理完成: 删除 {success}, 失败 {fail}')
    finally:
        await browser.close()


async def _cmd_clear_drafts(args: argparse.Namespace):
    """清空草稿箱所有章节（跳过已发布的）。
    
    适用场景：想清空草稿箱重新开始，但不删除已正式发布的章节。
    """
    from publisher.browser import Browser
    from publisher.config import resolve_book_id
    
    project_root = Path(args.project_root).expanduser().resolve()
    book_id = resolve_book_id(project_root, args.platform, getattr(args, 'book', None))
    
    adapter = _get_adapter(args.platform)
    browser = Browser(platform=args.platform)
    page = await browser.start()
    
    try:
        drafts = await adapter.get_all_drafts(page, book_id)
        if not drafts:
            print('草稿箱为空。')
            return
        
        print(f'准备删除全部 {len(drafts)} 篇草稿')
        if not getattr(args, 'yes', False):
            resp = _safe_input('确认清空草稿箱？(y/N): ', default='n')
            if resp.lower() != 'y':
                print('已取消。')
                return
        
        success = fail = skip = 0
        for d in drafts:
            item_id = str(d.get('item_id', ''))
            title = d.get('title', '')
            if await adapter.delete_draft(page, book_id, item_id):
                print(f'  [DEL] {title}')
                success += 1
            else:
                # 删除失败可能是已发布
                print(f'  [SKIP] {title} (可能已发布)')
                skip += 1
            await asyncio.sleep(0.5)
        
        print(f'\n清空完成: 删除 {success}, 跳过 {skip}')
    finally:
        await browser.close()


async def _cmd_delete_drafts(args: argparse.Namespace):
    """删除草稿箱所有章节（包括已发布的，需二次确认）。
    
    危险操作：会删除所有草稿，包括已发布状态的章节。
    """
    from publisher.browser import Browser
    from publisher.config import resolve_book_id, get_log_path
    
    project_root = Path(args.project_root).expanduser().resolve()
    book_id = resolve_book_id(project_root, args.platform, getattr(args, 'book', None))
    project_name = project_root.name
    
    adapter = _get_adapter(args.platform)
    browser = Browser(platform=args.platform)
    page = await browser.start()
    
    try:
        drafts = await adapter.get_all_drafts(page, book_id)
        if not drafts:
            print('草稿箱为空。')
            return
        
        print(f'找到 {len(drafts)} 个章节:')
        for ch in drafts[:5]:
            print(f'  - {ch.get("title", "未知")}')
        if len(drafts) > 5:
            print(f'  ... 共 {len(drafts)} 章')
        
        if not getattr(args, 'yes', False):
            resp = _safe_input(f'确认删除全部 {len(drafts)} 章？(yes/N): ', default='n')
            if resp.lower() != 'yes':
                print('已取消。')
                return
        
        success = fail = 0
        for ch in drafts:
            item_id = str(ch.get('item_id', '') or ch.get('article_id', ''))
            title = ch.get('title', '未知')
            if not item_id:
                print(f'  [SKIP] {title} 无 item_id')
                fail += 1
                continue
            
            if await adapter.delete_draft(page, book_id, item_id):
                print(f'  [DEL] {title}')
                success += 1
            else:
                print(f'  [FAIL] {title}')
                fail += 1
            await asyncio.sleep(1)
        
        print(f'\n删除完成: 成功 {success}, 失败 {fail}')
        
        # 清除上传记录
        if success > 0:
            log_path = get_log_path(args.platform, book_id, project_name)
            if log_path.is_file():
                log_path.unlink()
                print('上传记录已清除。')
    finally:
        await browser.close()


async def _cmd_publish_drafts(args: argparse.Namespace):
    """发布草稿箱中的章节（将草稿改为已发布状态）。

    适用场景：章节已在草稿箱，想批量发布到正式站。
    严格按章节号配对草稿的 item_id；标题和内容从本地文件读取。
    任一章节未成功发布都会返回非 0 退出码。
    """
    from publisher.browser import Browser
    from publisher.config import resolve_book_id
    from publisher.formatter import format_for_platform

    project_root = Path(args.project_root).expanduser().resolve()
    book_id = resolve_book_id(project_root, args.platform, getattr(args, 'book', None))

    chapter_indices = _parse_range(args.range, project_root)
    if not chapter_indices:
        print('未找到匹配的章节文件。')
        sys.exit(1)

    adapter = _get_adapter(args.platform)
    browser = Browser(platform=args.platform)
    page = await browser.start()

    try:
        drafts = await adapter.get_all_drafts(page, book_id)
        if not drafts:
            print('草稿箱为空，无法发布。请先上传章节。')
            sys.exit(1)

        if not getattr(args, 'yes', False):
            resp = _safe_input('继续发布？(Y/n): ', default='y')
            if resp.lower() in ('n', 'no'):
                print('已取消。')
                sys.exit(1)

        # P0 修复：建立 {章号: 草稿} 映射严格配对。
        # 旧实现 drafts.sort() 之后用 draft_queue.pop(0) 顺序取草稿，排序结果
        # 从未被使用，于是「第17章正文」会被写进草稿箱里最靠前那篇（如第37章）
        # 的 item_id，触发平台「重复标题和段落」校验，或直接把错误内容发出去。
        def _extract_chapter_num(draft):
            m = re.search(r'第\s*(\d+)\s*章', draft.get('title', ''))
            return int(m.group(1)) if m else 0

        def _draft_ts(draft):
            return draft.get('modify_time') or draft.get('create_time') or 0

        draft_by_num = {}
        unnumbered = 0
        for d in drafts:
            n = _extract_chapter_num(d)
            if n <= 0:
                unnumbered += 1
                continue
            prev = draft_by_num.get(n)
            if prev is not None:
                print(f'  [WARN] 草稿箱第{n}章存在重复草稿，保留最新一篇')
                if _draft_ts(d) > _draft_ts(prev):
                    draft_by_num[n] = d
                continue
            draft_by_num[n] = d

        if unnumbered:
            print(f'  [WARN] {unnumbered} 篇草稿标题解析不出章号，已忽略')

        missing = [n for n in chapter_indices if n not in draft_by_num]
        paired = len(chapter_indices) - len(missing)
        print(f'草稿箱: {len(drafts)} 篇, 待发布: {len(chapter_indices)} 章, 已配对: {paired} 章')
        if missing:
            print(f'  [WARN] 草稿箱缺少这些章节的草稿: {missing}')

        use_ai = getattr(args, 'use_ai', None)
        timer_time = 0
        if getattr(args, 'schedule_at', None):
            from datetime import datetime
            timer_time = int(datetime.strptime(args.schedule_at, '%Y-%m-%d %H:%M').timestamp())
            print(f'定时发布目标: {args.schedule_at} (unix {timer_time})')

        # 章间间隔（秒）。--interval 未传时保持历史默认 5.0。
        _gap = float(getattr(args, 'interval', 5.0) or 5.0)
        print(f'章间间隔: {_gap} 秒')

        success_count = fail_count = 0
        for idx in chapter_indices:
            draft = draft_by_num.get(idx)
            if draft is None:
                print(f'  [FAIL] 第{idx}章 草稿箱无对应草稿，跳过（不会拿其他章节的草稿顶替）')
                fail_count += 1
                continue

            chapter_file = _find_chapter_file(project_root, idx)
            if not chapter_file:
                print(f'  [WARN] 第{idx}章文件未找到，跳过')
                fail_count += 1
                continue

            raw_md = chapter_file.read_text(encoding='utf-8')
            title = _extract_title(raw_md) or f'第{idx}章'
            raw_md = _strip_heading_line(raw_md)
            content = format_for_platform(raw_md, args.platform)

            # 标题格式化（番茄要求 5-30 字符）
            clean_title = re.sub(r'^第\s*[\d零一二三四五六七八九十百千]+\s*章\s*', '', title).strip()
            # 部分项目标题写成「第1章：镜中符文」，剥掉章号后残留前导冒号，
            # 会发成「第 1 章 ：镜中符文」。统一去掉前导标点再拼标题。
            clean_title = clean_title.lstrip('：:、，,。.·—－-　 ').strip()
            if not clean_title:
                # 正文 md 首行没有「# 第N章 标题」时回退到文件名取标题。
                # 否则 title 只剩「第N章」，clean_title 为空，发出去的标题是
                # 「第 N 章 」——平台会以「标题长度不符合规范」整批拒绝。
                _m = re.match(r'^第\s*\d+\s*章[-—－\s　]+(.+?)\.md$', chapter_file.name)
                if _m:
                    clean_title = _m.group(1).strip()
            full_title = f'第 {idx} 章 {clean_title}'
            if len(full_title) > 30:
                full_title = full_title[:30]

            item_id = str(draft.get('item_id', ''))
            vol_spec = getattr(args, 'volume', None)
            ok = await adapter.publish_draft(page, book_id, item_id, full_title, content,
                                             use_ai=use_ai, timer_time=timer_time,
                                             volume=vol_spec)
            if ok:
                when = f' [定时 {args.schedule_at}]' if getattr(args, 'schedule_at', None) else ''
                print(f'  [PUB] 第{idx}章 {full_title}{when}')
                success_count += 1
            else:
                print(f'  [FAIL] 第{idx}章')
                fail_count += 1

            await asyncio.sleep(_gap)  # 章间间隔，避免触发反爬

        print(f'\n发布完成: 成功 {success_count}, 失败 {fail_count}')
        if fail_count > 0 or success_count == 0:
            print('[ERROR] 存在未成功发布的章节，返回非 0 退出码，调用方请勿推进进度。')
            sys.exit(1)
    finally:
        await browser.close()


def _safe_input(prompt: str, default: str = "y") -> str:
    """Wrap input() with EOFError guard for non-TTY environments."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n[非交互环境] 输入不可用，使用默认值: {default}")
        return default


def _read_book_meta(project_root: Path):
    from publisher.base import BookMeta
    state_file = project_root / ".webnovel" / "state.json"
    meta = BookMeta(title="", genre="", synopsis="", protagonist="")
    if state_file.is_file():
        # P2 修复：直读改走 read_json_safe（并发 os.replace 中途容错 + 失败降级 {}）
        try:
            from security_utils import read_json_safe
        except ImportError:  # pragma: no cover
            from scripts.security_utils import read_json_safe
        s = read_json_safe(state_file, default={})
        proj_info = s.get("project_info", {}) if isinstance(s, dict) else {}
        meta.title = proj_info.get("title", "") or project_root.name
        meta.genre = proj_info.get("genre", "")
        protag = s.get("protagonist_state", {}) if isinstance(s, dict) else {}
        meta.protagonist = protag.get("name", "") if isinstance(
            protag, dict) else ""
        meta.synopsis = proj_info.get("synopsis", "")
    return meta


def _parse_range(spec: str, project_root: Path) -> list[int]:
    import re
    if spec.lower() == "all":
        text_dir = project_root / "正文"
        if text_dir.is_dir():
            nums = []
            for f in sorted(text_dir.rglob("第*章*.md")):
                m = re.match(r"第(\d+)章", f.name)
                if m:
                    nums.append(int(m.group(1)))
            return nums
        return []

    result: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = part.split("-", 1)
                result.update(range(int(a), int(b) + 1))
            else:
                result.add(int(part))
        except ValueError:
            print(f"ERROR: 无效的章节范围 '{part}'，应为数字或范围（如 32-37）", file=sys.stderr)
            raise SystemExit(1)
    return sorted(result)


def _strip_heading_line(md: str) -> str:
    """剔除首行标题，避免正文里重复出现标题。

    兼容两种写法：
      1) Markdown 标题  「# 第XX章 标题」
      2) 纯文本标题行    「第XX章 标题」（部分项目的正文 md 首行是这种，
         没有 # 号，旧实现识别不了，会把标题当正文一起发上去）
    """
    import re
    lines = md.splitlines()
    if lines:
        first = lines[0].strip()
        if first.startswith("#") and re.search(r'第\s*\d+\s*章', first):
            return '\n'.join(lines[1:]).lstrip('\n')
        # 纯文本标题行：形如「第599章 没有直播的一顿饭」，短且独立成行
        if re.match(r'^第\s*\d+\s*章[\s　]', first) and len(first) <= 60:
            return '\n'.join(lines[1:]).lstrip('\n')
    return md


def _extract_title(md: str) -> str:
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _find_chapter_file(project_root: Path, index: int) -> Path | None:
    """在正文目录中定位章节文件。优先按卷目录查找，避免多卷同名冲突。"""
    import re
    text_dir = project_root / "正文"
    if not text_dir.is_dir():
        return None

    def _match(f):
        return re.match(rf"第0*{index}章", f.name)

    # 优先在当前卷目录查找（与 chapter_paths.volume_num_for_chapter 默认 50 章/卷一致）
    try:
        from chapter_paths import volume_num_for_chapter
    except ImportError:  # pragma: no cover
        from scripts.chapter_paths import volume_num_for_chapter
    vol = volume_num_for_chapter(index)
    vol_dir = text_dir / f"第{vol}卷"
    if vol_dir.is_dir():
        for f in sorted(vol_dir.iterdir()):
            if f.is_file() and f.suffix == ".md" and _match(f):
                return f

    # 回退到正文根目录
    for f in sorted(text_dir.iterdir()):
        if f.is_file() and f.suffix == ".md" and _match(f):
            return f

    # 最后递归搜索（兼容旧结构）
    for f in sorted(text_dir.rglob("*.md")):
        if _match(f):
            return f
    return None


def main():
    parser = argparse.ArgumentParser(description="小说自动发布")
    parser.add_argument("--project-root", type=Path, default=Path("."),
                        help="书项目根目录")
    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("setup-auth", help="引导登录指定平台")
    p_setup.add_argument("--platform", required=True,
                         help="平台名称 (fanqie)")

    p_list = sub.add_parser("list-books", help="列出已有书单")
    p_list.add_argument("--platform", required=True, help="平台名称")

    p_vols = sub.add_parser("list-volumes", help="列出书籍的全部分卷及章节数")
    p_vols.add_argument("--platform", required=True, choices=['fanqie'], help="平台名称")
    p_vols.add_argument("--book", default=None, help="书籍 ID（未指定时从项目绑定读取）")

    p_cvol = sub.add_parser("create-volume", help="新建分卷（卷名以大纲定义为准）")
    p_cvol.add_argument("name", help="完整卷名，如「第三卷：九宗试炼」")
    p_cvol.add_argument("--platform", required=True, choices=['fanqie'], help="平台名称")
    p_cvol.add_argument("--book", default=None, help="书籍 ID（未指定时从项目绑定读取）")
    p_cvol.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    p_create = sub.add_parser("create-book", help="创建新书")
    p_create.add_argument("--platform", required=True, help="平台名称")
    p_create.add_argument("--abstract", default=None, help="书籍简介（默认自动生成）")
    p_create.add_argument("--yes", action="store_true", help="跳过交互确认")

    p_upload = sub.add_parser("upload", help="上传章节")
    p_upload.add_argument("--platform", required=True, help="平台名称")
    p_upload.add_argument("--book", default=None, help="书籍 ID 或书名（未指定时从项目绑定读取）")
    p_upload.add_argument("--range", default="all", help="章节范围")
    p_upload.add_argument("--mode", default="draft", choices=["draft"],
                          help="发布模式 (目前仅支持草稿)")
    p_upload.add_argument("--yes", action="store_true",
                          help="跳过交叉校验的交互确认")

    # 草稿管理命令
    p_clean = sub.add_parser("clean-drafts", 
                             help="清理草稿箱重复章节（同章节号保留最新）")
    p_clean.add_argument("--platform", required=True, choices=['fanqie'], help="平台名称")
    p_clean.add_argument("--book", default=None, help="书籍 ID（未指定时从项目绑定读取）")
    p_clean.add_argument("--dry-run", action="store_true", help="预览模式，不执行实际删除")
    p_clean.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    p_clear = sub.add_parser("clear-drafts",
                            help="清空草稿箱所有章节（跳过已发布）")
    p_clear.add_argument("--platform", required=True, choices=['fanqie'], help="平台名称")
    p_clear.add_argument("--book", default=None, help="书籍 ID（未指定时从项目绑定读取）")
    p_clear.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    p_delete = sub.add_parser("delete-drafts",
                             help="删除草稿箱全部章节（危险操作，需二次确认）")
    p_delete.add_argument("--platform", required=True, choices=['fanqie'], help="平台名称")
    p_delete.add_argument("--book", default=None, help="书籍 ID（未指定时从项目绑定读取）")
    p_delete.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    p_publish = sub.add_parser("publish-drafts",
                              help="发布草稿箱中的章节（将草稿改为已发布状态）")
    p_publish.add_argument("--platform", required=True, choices=['fanqie'], help="平台名称")
    p_publish.add_argument("--book", default=None, help="书籍 ID（未指定时从项目绑定读取）")
    p_publish.add_argument("--schedule-at", default=None,
                           help="定时发布时间 YYYY-MM-DD HH:MM（不传则立即发布）")
    p_publish.add_argument("--use-ai", type=int, default=None, choices=[0, 1, 2],
                           help="「是否使用AI」声明：1=是，0=否（据真实抓包确认）")
    p_publish.add_argument("--range", default="all", help="章节范围")
    p_publish.add_argument("--volume", default=None,
                           help="目标卷：volume_id 或卷名（如「第二卷」，支持模糊匹配，需唯一命中；不传=第一个卷）")
    p_publish.add_argument("--interval", type=float, default=5.0,
                           help="章间间隔秒数，默认 5.0（防风控；如 10 表示每章间隔 10 秒）")
    p_publish.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    args = parser.parse_args()

    cmd_map = {
        "setup-auth": _cmd_setup_auth,
        "list-books": _cmd_list_books,
        "list-volumes": _cmd_list_volumes,
        "create-volume": _cmd_create_volume,
        "create-book": _cmd_create_book,
        "upload": _cmd_upload,
        "clean-drafts": _cmd_clean_drafts,
        "clear-drafts": _cmd_clear_drafts,
        "delete-drafts": _cmd_delete_drafts,
        "publish-drafts": _cmd_publish_drafts,
    }
    handler = cmd_map.get(args.command)
    if handler:
        asyncio.run(handler(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
