"""独立全量复核：一批修订章是否真的同步（而非假推送）。

判定逻辑（三方对照，最严密）：
  线上 vs 本地(新版) vs 备份(改前旧版)

  - 线上 == 本地        → 真同步
  - 线上 == 备份(≠本地) → 假推送，线上还是旧版
  - 两者都不等          → 内容错乱，需人工看

备份目录默认取「改前备份」最新一期（发布/线上备份_改前_*、发布/草稿备份_改前_*），
也可用 --backup-online / --backup-draft 显式指定。

用法：
  python verify_true_sync.py --chapters 96,121,152   # 指定章节
  python verify_true_sync.py --chapters 1-60         # 范围
  python verify_true_sync.py                         # 本地全部章节
"""
import asyncio
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from publisher.adapters.fanqie import _text_to_html  # noqa: E402
from publisher.browser import Browser  # noqa: E402
from publisher.formatter import format_for_platform  # noqa: E402

from project_paths import project_root, bound_book_id  # noqa: E402

ROOT = project_root()
BOOK_ID = bound_book_id(ROOT)


def _backup_dir(plain: str, dated_pat: str) -> Path:
    """优先取最新一期「改前备份」目录，没有则退回常规备份目录。"""
    base = ROOT / "发布"
    hits = sorted(base.glob(dated_pat))
    return hits[-1] if hits else base / plain


BK_ONLINE = _backup_dir("线上备份", "线上备份_改前_*")
BK_DRAFT = _backup_dir("草稿备份", "草稿备份_改前_*")


def parse_ranges(spec: str) -> list[int]:
    """'1-60,96,121' → [1..60, 96, 121]"""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def all_local_chapters() -> list[int]:
    """本地 正文/ 下全部章节号。"""
    chs = []
    for f in (ROOT / "正文").glob("第*章-*.md"):
        m = re.match(r"第(\d+)章", f.name)
        if m:
            chs.append(int(m.group(1)))
    return sorted(set(chs))


def norm(s: str) -> str:
    """剥 HTML 标签 + 去所有空白，只比文字。"""
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", "", html.unescape(s))


def local_plain(ch: int) -> str:
    fs = sorted((ROOT / "正文").glob(f"第{ch:04d}章-*.md"))
    if not fs:
        return ""
    txt = fs[0].read_text(encoding="utf-8")
    # 去掉首行标题行（与发布链路一致）
    lines = txt.split("\n")
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]
    return norm(format_for_platform("\n".join(lines), "fanqie"))


def backup_plain(ch: int) -> str | None:
    for base in (BK_ONLINE, BK_DRAFT):
        f = base / f"第{ch:04d}章.json"
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            return norm(d.get("content", ""))
    return None


async def main():
    import argparse
    ap = argparse.ArgumentParser(description="三方对照复核：线上 vs 本地 vs 改前备份")
    ap.add_argument("--chapters", default=None,
                    help="要复核的章节，如 96,121,152 或 1-60；缺省为本地全部章节")
    ap.add_argument("--backup-online", default=None, help="改前备份目录（已发布/定时章）")
    ap.add_argument("--backup-draft", default=None, help="改前备份目录（草稿箱章）")
    args = ap.parse_args()

    global BK_ONLINE, BK_DRAFT
    if args.backup_online:
        BK_ONLINE = Path(args.backup_online)
    if args.backup_draft:
        BK_DRAFT = Path(args.backup_draft)
    chapters = parse_ranges(args.chapters) if args.chapters else all_local_chapters()
    print(f"[info] 项目根目录: {ROOT}")
    print(f"[info] 备份目录: 线上={BK_ONLINE}  草稿={BK_DRAFT}")
    print(f"[info] 待复核 {len(chapters)} 章")

    br = Browser(platform="fanqie")
    page = await br.start()
    try:
        await page.goto("https://fanqienovel.com/main/writer/",
                        wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        # ---- 拉卷列表 ----
        res = await page.evaluate("""async ([bid]) => {
            const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',book_id:bid});
            const r = await fetch('https://fanqienovel.com/api/author/volume/volume_list/v1/?'+p,
                {credentials:'include'});
            return await r.json();
        }""", [BOOK_ID])
        vlist = (res.get("data") or {}).get("volume_list") or []
        print(f"[info] 卷 {len(vlist)} 个")

        # ---- 拉线上索引：{章号: (item_id, title)} ----
        idx: dict[int, tuple[str, str]] = {}
        for v in vlist:
            vid = v.get("volume_id")
            for pi in range(0, 40):
                r2 = await page.evaluate("""async ([bid, vid, pi]) => {
                    const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                        book_id:bid, volume_id:vid, page_index:String(pi), page_count:'50'});
                    const r = await fetch('https://fanqienovel.com/api/author/chapter/chapter_list/v1/?'+p,
                        {credentials:'include'});
                    return await r.json();
                }""", [BOOK_ID, vid, pi])
                items = (r2.get("data") or {}).get("item_list") or []
                if not items:
                    break
                for it in items:
                    m = re.search(r"第\s*(\d+)\s*章", it.get("title", ""))
                    if m:
                        idx[int(m.group(1))] = (str(it.get("item_id", "")),
                                                it.get("title", ""))
                if len(items) < 50:
                    break
        print(f"[info] 线上索引 {len(idx)} 章")

        # ---- 拉草稿索引 ----
        didx: dict[int, tuple[str, str]] = {}
        for pi in range(0, 40):
            r3 = await page.evaluate("""async ([bid, pi]) => {
                const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                    book_id:bid, page_index:String(pi), page_count:'15'});
                const r = await fetch('https://fanqienovel.com/api/author/chapter/draft_list/v1/?'+p,
                    {credentials:'include'});
                return await r.json();
            }""", [BOOK_ID, pi])
            items = (r3.get("data") or {}).get("draft_list") or []
            if not items:
                break
            for it in items:
                m = re.search(r"第\s*(\d+)\s*章", it.get("title", ""))
                if m:
                    didx[int(m.group(1))] = (str(it.get("item_id", "")),
                                             it.get("title", ""))
            if len(items) < 15:
                break
        print(f"[info] 草稿索引 {len(didx)} 篇")

        # ---- 逐章三方对照 ----
        ok, fake, broken, noitem = [], [], [], []
        for ch in chapters:
            item = idx.get(ch) or didx.get(ch)
            if not item:
                noitem.append(ch)
                print(f"  {ch:>4}  ⚠️  线上无此章节")
                continue
            item_id = item[0]
            r4 = await page.evaluate("""async ([bid, iid]) => {
                const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                    book_id:bid, item_id:iid, from_source:'0'});
                const r = await fetch('https://fanqienovel.com/api/author/edit_article/v0/?'+p,
                    {credentials:'include'});
                return await r.json();
            }""", [BOOK_ID, item_id])
            online = norm((r4.get("data") or {}).get("content", ""))
            local = local_plain(ch)
            backup = backup_plain(ch)

            if not online:
                broken.append(ch)
                print(f"  {ch:>4}  ⚠️  线上正文读为空（可能是复审过渡态）")
            elif online == local:
                ok.append(ch)
            elif backup is not None and online == backup:
                fake.append(ch)
                print(f"  {ch:>4}  ❌ 假推送：线上仍等于改前备份")
            else:
                broken.append(ch)
                print(f"  {ch:>4}  ⚠️  内容错乱：线上≠本地 且 ≠备份")
            await asyncio.sleep(0.25)

        print()
        print("=" * 62)
        print(f"复核章数        : {len(chapters)}")
        print(f"真同步(线上=本地): {len(ok)}")
        print(f"假推送(线上=旧版): {len(fake)}  {fake}")
        print(f"异常/读空        : {len(broken)}  {broken}")
        print(f"线上无此章       : {len(noitem)}  {noitem}")
        print("=" * 62)
    finally:
        await br.close()


asyncio.run(main())
