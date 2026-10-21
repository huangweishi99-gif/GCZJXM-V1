"""定额本全量 OCR: 参数化渲染+分批 OCR, 断点续跑。
用法:
  python quota_full.py render --pdf <pdf> --work <dir>          # 全量渲染(跳过已有)
  python quota_full.py ocr --work <dir> [--start 0] [--end N] [--batch 80]  # 分批 OCR
  python quota_full.py lines --work <dir> --pages 10,11,12     # 看指定页版式
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import fitz

BASE = Path(r"d:\projects\cost-estimation\清单数据资料\AI学习清单\广联达定额\2026年9月信息价_提取\pipeline")
PS1 = BASE / "ocr_batch.ps1"


def cmd_render(a):
    doc = fitz.open(a.pdf)
    n = doc.page_count
    png_dir = Path(a.work) / "png"
    png_dir.mkdir(parents=True, exist_ok=True)
    todo = [p for p in range(n) if not (png_dir / f"page_{p + 1:03d}.png").exists()]
    print(f"总页数 {n}, 待渲染 {len(todo)}")
    t0 = time.time()
    for i, pno in enumerate(todo):
        pix = doc[pno].get_pixmap(dpi=300)
        pix.save(png_dir / f"page_{pno + 1:03d}.png")
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    doc.close()
    print(f"渲染完成  {time.time() - t0:.0f}s")


def cmd_ocr(a):
    png_dir = Path(a.work) / "png"
    json_root = Path(a.work) / "json"
    json_root.mkdir(parents=True, exist_ok=True)
    pngs = sorted(png_dir.glob("*.png"))
    start, end = a.start, a.end if a.end else len(pngs)
    todo = [p for p in pngs[start:end] if not (json_root / (p.stem + ".json")).exists()]
    print(f"OCR 范围 [{start},{end}) 待识别 {len(todo)} 页")
    t0 = time.time()
    done = 0
    for i in range(0, len(todo), a.batch):
        chunk = todo[i:i + a.batch]
        bdir = Path(a.work) / "_batch"
        bpng, bjson = bdir / "png", bdir / "json"
        bpng.mkdir(parents=True, exist_ok=True)
        bjson.mkdir(parents=True, exist_ok=True)
        for old in bpng.glob("*.png"):
            old.unlink()
        for p in chunk:
            (bpng / p.name).write_bytes(p.read_bytes())
        r = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(PS1),
             "-PngDir", str(bpng), "-JsonDir", str(bjson)],
            capture_output=True, text=True, timeout=1200)
        out = (r.stdout or "") + (r.stderr or "")
        for jf in bjson.glob("*.json"):
            jf.replace(json_root / jf.name)
        done += out.count("OK page")
        print(f"  {done} 页  {time.time() - t0:.0f}s  (本批 OK={out.count('OK page')} FAIL={out.count('FAIL')})", flush=True)
    shutil_cleanup(Path(a.work) / "_batch")
    print(f"OCR 完成  {time.time() - t0:.0f}s")


def shutil_cleanup(d):
    if d.exists():
        for p in sorted(d.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        d.rmdir()


def cmd_lines(a):
    json_root = Path(a.work) / "json"
    for pno in [int(x) for x in a.pages.split(",")]:
        jf = json_root / f"page_{pno:03d}.json"
        if not jf.exists():
            print(f"{jf.name} 不存在"); continue
        data = json.loads(jf.read_text(encoding="utf-8-sig"))
        words = [w for ln in data["lines"] for w in ln["words"]]
        rows = []
        for w in sorted(words, key=lambda w: (w["y"] + w["h"] / 2, w["x"])):
            cy = w["y"] + w["h"] / 2
            if rows and abs(cy - rows[-1][0]) < 28:
                rows[-1][1].append(w)
            else:
                rows.append([cy, [w]])
        print(f"\n===== page_{pno:03d} ({len(words)} 词) =====")
        for cy, ws in rows[:40]:
            ws.sort(key=lambda w: w["x"])
            print("  " + " ".join(w["t"] for w in ws)[:95])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render"); r.add_argument("--pdf", required=True); r.add_argument("--work", required=True)
    o = sub.add_parser("ocr"); o.add_argument("--work", required=True)
    o.add_argument("--start", type=int, default=0); o.add_argument("--end", type=int, default=0)
    o.add_argument("--batch", type=int, default=80)
    l = sub.add_parser("lines"); l.add_argument("--work", required=True); l.add_argument("--pages", required=True)
    a = ap.parse_args()
    {"render": cmd_render, "ocr": cmd_ocr, "lines": cmd_lines}[a.cmd](a)
