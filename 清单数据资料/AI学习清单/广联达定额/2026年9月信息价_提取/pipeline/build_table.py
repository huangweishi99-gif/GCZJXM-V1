"""OCR JSON -> 表头锚定列重建 -> 纠错 -> CSV。
核心：每页找表头词(序号/材料名称/型号规格/单位/价格)的x作列锚，
其余词按最近锚分配；列锚跨页传递（续表沿用）。
"""
import csv
import json
import re
from pathlib import Path

WORK = Path(r"d:\projects\cost-estimation\清单数据资料\AI学习清单\广联达定额\2026年9月信息价_提取")
JSON_DIR = WORK / "json"
OUT = WORK / "2026年9月深圳信息价.csv"

SEC = [(11, 57, "建筑材料价格"), (58, 99, "苗木花卉价格"), (100, 100, "装配式混凝土预制构件"),
       (101, 101, "定额人工费指数及工日价格"), (102, 104, "市场劳务价格"), (105, 107, "租赁价格")]

def section(page: int) -> str:
    for a, b, name in SEC:
        if a <= page <= b:
            return name
    return "其他"

NUM_FIX = {"·": ".", "．": ".", "，": ".", ",": ".", "、": ".", "&": ".", "。": ".",
           "L": "1", "l": "1", "丿": "1", "I": "1", "丨": "1", "伍": ".", "O": "0",
           "o": "0", "Q": "0", "D": "0", "S": "5", "s": "5", "B": "8", "g": "9",
           "Z": "2", "G": "6", "馬": "", "元": "", "￥": "", " ": ""}

def fix_price(s: str):
    raw = "".join(NUM_FIX.get(ch, ch) for ch in s)
    m = re.fullmatch(r"(\d+)\.(\d{1,2})", raw)
    if m:
        return f"{m.group(1)}.{m.group(2):0<2}", True
    if re.fullmatch(r"\d+", raw):
        d = raw
        if len(d) >= 5:
            return f"{d[:-2]}.{d[-2:]}", True
        return d + ".00", True
    digits = re.findall(r"\d", raw)
    if len(digits) >= 5:
        d = "".join(digits)
        return f"{d[:-2]}.{d[-2:]}", True
    return raw, False

def clean_text(s: str) -> str:
    return s.replace(" ", "").replace("小", "φ")

HEAD_KEYS = [
    ("seq", ("序号", "序号称")),
    ("name", ("材料名称", "材料名称名称", "名称", "工程项目", "项目")),
    ("code", ("编码", "编号", "项目编码")),
    ("spec", ("型号规格", "规格型号", "规格")),
    ("unit", ("单位", "计量单位")),
    ("price", ("价格（元）", "价格(元)", "价格", "单价", "含税价", "综合单价", "工日单价", "日工资")),
]

def find_anchors(words):
    """页面上部词聚成行->拼接->找命中关键词最多的行(>=2个)->按词偏移映射取各key的x锚。"""
    page_h = max(w["y"] + w["h"] for w in words) if words else 1
    top = sorted([w for w in words if w["y"] < page_h * 0.35], key=lambda w: (w["y"] + w["h"] / 2, w["x"]))
    lines = []
    for w in top:
        cy = w["y"] + w["h"] / 2
        if lines and abs(cy - lines[-1]["cy"]) < 25:
            lines[-1]["ws"].append(w)
            n = len(lines[-1]["ws"])
            lines[-1]["cy"] = (lines[-1]["cy"] * (n - 1) + cy) / n
        else:
            lines.append({"cy": cy, "ws": [w]})

    best = None  # (命中数, 行)
    for ln in lines:
        ws = sorted(ln["ws"], key=lambda w: w["x"])
        text = "".join(w["t"].strip() for w in ws)
        keys = set()
        for key, kws in HEAD_KEYS:
            if any(kw in text for kw in kws):
                keys.add(key)
        if best is None or len(keys) > best[0]:
            best = (len(keys), ln, text)
    if best is None or best[0] < 2:
        return {}

    ln = best[1]
    ws = sorted(ln["ws"], key=lambda w: w["x"])
    toks = [w["t"].strip() for w in ws]
    text = "".join(toks)
    # char 偏移 -> 词索引
    c2w = []
    for i, t in enumerate(toks):
        c2w.extend([i] * max(len(t), 1))
    anchors = {}
    for key, kws in HEAD_KEYS:
        for kw in kws:
            s = text.find(kw)
            if s >= 0:
                e = s + len(kw)
                idx = [c2w[min(c, len(c2w) - 1)] for c in range(s, e)]
                xs = [ws[i]["x"] + ws[i]["w"] / 2 for i in idx]
                anchors[key] = sum(xs) / len(xs)
                break
    return anchors

rows = []
stats = {}
prev_anchors = {}
for jf in sorted(JSON_DIR.glob("page_*.json")):
    page = int(jf.stem.split("_")[1])
    data = json.loads(jf.read_text(encoding="utf-8-sig"))
    words = []
    for ln in data.get("lines", []):
        words.extend(ln.get("words", []))
    if not words:
        continue
    sec = section(page)
    stats.setdefault(sec, [0, 0])

    anchors = find_anchors(words)
    use = dict(prev_anchors.get(sec, {}))
    use.update(anchors)  # 本页表头优先
    if "price" not in use:
        continue  # 无价格锚，无法对齐（说明文字页）
    prev_anchors[sec] = use

    # 词 -> 列分配（按最近锚 x，边界取锚间中点）
    ax = sorted((v, k) for k, v in use.items())
    bounds = []
    for i in range(len(ax)):
        left = (ax[i - 1][0] + ax[i][0]) / 2 if i else -1e9
        right = (ax[i][0] + ax[i + 1][0]) / 2 if i < len(ax) - 1 else 1e9
        bounds.append((left, right, ax[i][1]))

    cols = {k: [] for _, _, k in bounds}
    for w in words:
        cx = w["x"] + w["w"] / 2
        cy = w["y"] + w["h"] / 2
        for lo, hi, k in bounds:
            if lo <= cx < hi:
                cols[k].append((cy, w["x"], w["t"]))
                break

    # 列内 y 聚类成单元格（阈值 30）
    def col_cells(items):
        items.sort()
        cells = []
        for cy, x, t in items:
            if cells and abs(cy - cells[-1][0]) < 30:
                cells[-1][1].append((x, t))
            else:
                cells.append([cy, [(x, t)]])
        return [(cy, "".join(t for _, t in sorted(ts))) for cy, ts in cells]

    cell_cols = {k: col_cells(v) for k, v in cols.items()}

    # 行锚：价格列单元格 y（价格行必有价格）
    for cy, ptext in cell_cols.get("price", []):
        price_raw = clean_text(ptext)
        price, ok = fix_price(price_raw)
        if not ok:
            continue
        def grab(key):
            best = min(((abs(c[0] - cy), c[1]) for c in cell_cols.get(key, [])), default=(9e9, ""))
            return best[1] if best[0] < 38 else ""
        seq = clean_text(grab("seq"))
        name = clean_text(grab("name"))
        spec = clean_text(grab("spec"))
        unit = clean_text(grab("unit"))
        code = clean_text(grab("code"))
        if not re.search(r"[一-鿿A-Za-z]", name):
            continue
        stats[sec][0] += 1
        stats[sec][1] += 1 if ok else 0
        rows.append({"页": page, "栏目": sec, "类别": "",
                     "序号": seq if re.fullmatch(r"\d{1,4}", seq) else "",
                     "编码": code, "材料名称": name, "规格": spec, "单位": unit,
                     "价格": price, "价格原文": price_raw, "有效": "是" if ok else ""})

    # 分类行：在名称列、无价格行伴随、短中文
    name_cells = cell_cols.get("name", [])
    price_ys = [c[0] for c in cell_cols.get("price", [])]
    for cy, ntext in name_cells:
        t = clean_text(ntext)
        if (re.fullmatch(r"[一-鿿、（）()A-Za-z0-9]{2,14}", t)
                and not any(ch in t for ch in "，。、；：")
                and not any(abs(cy - py) < 30 for py in price_ys)
                and not re.fullmatch(r"\d+(\.\d+)?", t)):
            rows.append({"页": page, "栏目": sec, "类别": t, "序号": "", "编码": "",
                         "材料名称": "", "规格": "", "单位": "", "价格": "", "价格原文": "", "有效": ""})

with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["栏目", "类别", "序号", "编码", "材料名称", "规格", "单位", "价格", "价格原文", "有效", "页"])
    w.writeheader()
    for r in rows:
        w.writerow(r)

print(f"总行数: {len(rows)}  -> {OUT.name}")
for sec, (total, valid) in stats.items():
    print(f"  {sec}: 数据行 {total} (价格有效 {valid})")
