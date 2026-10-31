#!/usr/bin/env python3
"""回读指定章节线上正文，与本地 md 比对（验证定时发布的内容是否真的落库）。"""
from __future__ import annotations
import argparse, asyncio, html, json, re, sys
from pathlib import Path
SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from publisher.browser import Browser  # noqa: E402

BOOK_ID = bound_book_id(ROOT)
from project_paths import project_root, bound_book_id  # noqa: E402
ROOT = project_root()


def norm(s: str) -> str:
    return re.sub(r"\s+", "", html.unescape(s or ""))


def strip_tags(s: str) -> str:
    """线上正文是 <p> 包裹的 HTML，比对前剥标签只留纯文本。"""
    t = re.sub(r"</p>", "\n", s or "")
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--range", required=True)
    args = ap.parse_args()
    if "-" in args.range:
        a, b = args.range.split("-")
        nums = list(range(int(a), int(b) + 1))
    else:
        nums = [int(x) for x in args.range.split(",")]

    # 按卷拉chapter_list → {章号: item_id}
    vols: list[str] = []
    br = Browser(headless=True, platform="fanqie")
    page = await br.start()
    try:
        for attempt in range(4):
            try:
                await page.goto("https://fanqienovel.com/main/writer/",
                                wait_until="domcontentloaded", timeout=60_000)
                await asyncio.sleep(3)
                break
            except Exception:
                await asyncio.sleep(3)
        vols_res = await page.evaluate(
            """async (book_id) => {
                const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',book_id});
                const r = await fetch('https://fanqienovel.com/api/author/volume/volume_list/v1/?'+p,
                    {credentials:'include'});
                return await r.json();
            }""", BOOK_ID)
        vols = [str(v["volume_id"])
                for v in (vols_res.get("data") or {}).get("volume_list") or []]
        print(f"  [debug] 卷 {len(vols)} 个")
        idx = {}
        for vid in vols:
            for pi in range(0, 20):
                res = await page.evaluate(
                    """async ([bid, vid, pi]) => {
                        const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                            book_id:bid, volume_id:vid, page_index:String(pi), page_count:'50'});
                        const r = await fetch('https://fanqienovel.com/api/author/chapter/chapter_list/v1/?'+p,
                            {credentials:'include'});
                        return await r.json();
                    }""", [BOOK_ID, vid, pi])
                items = (res.get("data") or {}).get("item_list") or []
                print(f"  [debug] vol={vid[-6:]} pi={pi} 返回 {len(items)} 条 code={res.get('code')}")
                if not items:
                    break
                for it in items:
                    m = re.search(r"第\s*(\d+)\s*章", it.get("title", ""))
                    if m:
                        idx[int(m.group(1))] = it
                await asyncio.sleep(0.2)

        print(f"{'章':>4}  {'线上标题':<26} {'线上字数':>7} {'本地字数':>7}  一致?")
        print("-" * 76)
        bad = 0
        for n in nums:
            it = idx.get(n)
            if not it:
                print(f"{n:>4}  线上不存在")
                bad += 1
                continue
            res = await page.evaluate(
                """async ([bid, iid]) => {
                    const p = new URLSearchParams({aid:'2503',app_name:'muye_novel',
                        book_id:bid, item_id:iid, from_source:'0'});
                    const r = await fetch('https://fanqienovel.com/api/author/edit_article/v0/?'+p,
                        {credentials:'include'});
                    return await r.json();
                }""", [BOOK_ID, str(it.get("item_id"))])
            d = res.get("data") or {}
            online = norm(strip_tags(d.get("content", "")))
            f = sorted((ROOT / "正文").glob(f"第{n:04d}章-*.md"))
            # 与发布时推送的内容保持同一条处理链路：strip 标题行 → format_for_platform
            import publisher as _P
            from publisher.formatter import format_for_platform as _fmt
            local_raw = f[0].read_text(encoding="utf-8") if f else ""
            local_md = _P._strip_heading_line(local_raw) if f else ""
            local = norm(_fmt(local_md, "fanqie"))
            same = online == local and len(online) > 0
            if not same:
                bad += 1
            print(f"{n:>4}  {(d.get('title') or it.get('title',''))[:24]:<26} "
                  f"{len(online):>7} {len(local):>7}  {'✅' if same else '❌'}")
            if not same and len(online) > 0:
                k = next((i for i in range(min(len(online), len(local)))
                          if online[i] != local[i]), min(len(online), len(local)))
                print(f"        首个差异 @{k}: 线上『{online[max(0,k-25):k+25]}』")
                print(f"                      本地『{local[max(0,k-25):k+25]}』")
            await asyncio.sleep(0.4)
        print(f"\n不一致/缺失: {bad} 章")
        return 0 if bad == 0 else 1
    finally:
        await br.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
