"""主控：渲染 PDF 页 -> 分批调 Windows OCR -> 输出 JSON。
用法: python _ocr_master.py <起始PDF页> <结束PDF页>   (1-based, 含端点)
"""
import subprocess
import sys
import time
from pathlib import Path

import fitz

PDF = Path(r"d:\projects\cost-estimation\清单数据资料\AI学习清单\广联达定额\《深圳建设工程价格信息》2026年9月.pdf")
WORK = Path(r"d:\projects\cost-estimation\清单数据资料\AI学习清单\广联达定额\2026年9月信息价_提取")
PNG_DIR = WORK / "png"
JSON_DIR = WORK / "json"
PS1 = Path(r"d:\projects\cost-estimation\data\tmp\_ocr_batch.ps1")

p_start, p_end = int(sys.argv[1]), int(sys.argv[2])
PNG_DIR.mkdir(parents=True, exist_ok=True)
JSON_DIR.mkdir(parents=True, exist_ok=True)

doc = fitz.open(PDF)
t0 = time.time()
n_render = n_skip = 0
for pno in range(p_start - 1, p_end):
    png = PNG_DIR / f"page_{pno + 1:03d}.png"
    if png.exists() or (JSON_DIR / f"page_{pno + 1:03d}.json").exists():
        n_skip += 1
        continue
    pix = doc[pno].get_pixmap(dpi=300)
    pix.save(png)
    n_render += 1
doc.close()
print(f"渲染: {n_render} 页 (跳过 {n_skip})  {time.time() - t0:.0f}s", flush=True)

t1 = time.time()
r = subprocess.run(
    ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(PS1),
     "-PngDir", str(PNG_DIR), "-JsonDir", str(JSON_DIR)],
    capture_output=True, text=True, timeout=1800,
)
out = (r.stdout or "") + (r.stderr or "")
oks = out.count("OK page")
fails = out.count("FAIL")
print(f"OCR: OK={oks} FAIL={fails}  耗时 {time.time() - t1:.0f}s", flush=True)
for line in out.splitlines():
    if "FAIL" in line or "ENGINE" in line:
        print(" ", line[:100], flush=True)

# 清理已识别页对应的 PNG，控磁盘
n_clean = 0
for j in JSON_DIR.glob("*.json"):
    png = PNG_DIR / (j.stem + ".png")
    if png.exists():
        png.unlink()
        n_clean += 1
print(f"清理 PNG: {n_clean} 个", flush=True)
