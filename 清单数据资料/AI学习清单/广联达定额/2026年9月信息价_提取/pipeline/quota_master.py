"""定额本 OCR 试探: 渲染装饰定额前 4 页 -> OCR -> 看版式是否适配现有管线。
用法: python _quota_master.py
"""
import json
import subprocess
import time
from pathlib import Path

import fitz

PDF = Path(r"d:\projects\cost-estimation\清单数据资料\AI学习清单\广联达定额\装饰工程消耗量标准定额.pdf")
WORK = Path(r"d:\projects\cost-estimation\清单数据资料\AI学习清单\广联达定额\定额OCR_试探")
PNG_DIR = WORK / "png"
JSON_DIR = WORK / "json"
PS1 = Path(r"d:\projects\cost-estimation\清单数据资料\AI学习清单\广联达定额\2026年9月信息价_提取\pipeline\ocr_batch.ps1")
PAGES = [1, 2, 3, 5]  # 0-based: 封面后目录/正文开始页

PNG_DIR.mkdir(parents=True, exist_ok=True)
JSON_DIR.mkdir(parents=True, exist_ok=True)

doc = fitz.open(PDF)
print(f"总页数: {doc.page_count}")
t0 = time.time()
for pno in PAGES:
    png = PNG_DIR / f"page_{pno + 1:03d}.png"
    if not png.exists():
        pix = doc[pno].get_pixmap(dpi=300)
        pix.save(png)
doc.close()
print(f"渲染 {len(PAGES)} 页  {time.time() - t0:.0f}s")

t1 = time.time()
r = subprocess.run(
    ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(PS1),
     "-PngDir", str(PNG_DIR), "-JsonDir", str(JSON_DIR)],
    capture_output=True, text=True, timeout=600,
)
out = (r.stdout or "") + (r.stderr or "")
print(f"OCR: OK={out.count('OK page')} FAIL={out.count('FAIL')}  {time.time() - t1:.0f}s")

# 打印每页前 30 行文本看版式
for jf in sorted(JSON_DIR.glob("*.json")):
    data = json.loads(jf.read_text(encoding="utf-8-sig"))
    words = [w for ln in data["lines"] for w in ln["words"]]
    lines = []
    for w in sorted(words, key=lambda w: (w["y"] + w["h"] / 2, w["x"])):
        cy = w["y"] + w["h"] / 2
        if lines and abs(cy - lines[-1][0]) < 28:
            lines[-1][1].append(w)
        else:
            lines.append([cy, [w]])
    print(f"\n===== {jf.name} ({len(words)} 词) =====")
    for cy, ws in lines[:28]:
        ws.sort(key=lambda w: w["x"])
        print("  " + " ".join(w["t"] for w in ws)[:95])
