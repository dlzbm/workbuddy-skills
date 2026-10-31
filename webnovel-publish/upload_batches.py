#!/usr/bin/env python3
"""分批上传章节到草稿箱，每批 20 章，失败自动重试。

用法: python upload_batches.py 201-600 [--batch 20] [--retry 3]
"""
from __future__ import annotations
import argparse, asyncio, subprocess, sys, time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))

from project_paths import project_root  # noqa: E402

PY = sys.executable      # 当前解释器（需已安装 playwright）
SKILL = str(SKILL_DIR)   # 技能目录（本脚本所在目录）
ROOT = str(project_root())  # 小说项目根目录：自动探测，也可用 WEBHOVEL_PROJECT_ROOT 指定


def parse(s: str) -> list[int]:
    out: list[int] = []
    for p in s.split(","):
        if "-" in p:
            a, b = p.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(p))
    return out


def run_batch(chs: list[int]) -> tuple[bool, str]:
    cmd = [PY, "-X", "utf8", "publisher/__init__.py",
           "--project-root", ROOT, "upload",
           "--platform", "fanqie", "--range", f"{chs[0]}-{chs[-1]}",
           "--mode", "draft", "--yes"]
    r = subprocess.run(cmd, cwd=SKILL, capture_output=True, text=True, timeout=1800)
    out = (r.stdout or "") + (r.stderr or "")
    ok = r.returncode == 0 and "上传完成" in out
    return ok, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("range")
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--retry", type=int, default=3)
    args = ap.parse_args()

    chs = parse(args.range)
    print(f"待上传 {len(chs)} 章: {chs[0]}—{chs[-1]}，每批 {args.batch} 章")
    batches = [chs[i:i + args.batch] for i in range(0, len(chs), args.batch)]
    done, failed = 0, []
    for i, b in enumerate(batches, 1):
        ok = False
        for attempt in range(1, args.retry + 1):
            t0 = time.time()
            ok, out = run_batch(b)
            tag = "OK" if ok else "FAIL"
            print(f"[{i}/{len(batches)}] {b[0]}-{b[-1]}  第{attempt}次  {tag}  "
                  f"{time.time()-t0:.0f}s")
            if not ok:
                tail = "\n".join(out.strip().split("\n")[-3:])
                print(f"    {tail[:300]}")
            else:
                break
        if ok:
            done += len(b)
        else:
            failed.append((b[0], b[-1]))
        time.sleep(2)
    print(f"\n上传完成: {done} 章成功；失败批次 {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
