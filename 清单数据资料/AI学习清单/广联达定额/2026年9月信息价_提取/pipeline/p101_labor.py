"""p101 定额人工费指数及工日价格 —— 专用模板 v2（按词x坐标切列，弃用正则切粘连串）。
表B: 序号x<480 | 名称480-1050 | 单位1050-1900 | 价格x>1900
表A: 数字词按x间隙(>50px)切列, 取最后一列=2026年9月
"""
import csv
import json
import re
from pathlib import Path

WORK = Path(r"d:\projects\cost-estimation\清单数据资料\AI学习清单\广联达定额\2026年9月信息价_提取")
data = json.loads((WORK / "json" / "page_101.json").read_text(encoding="utf-8-sig"))
words = [w for ln in data["lines"] for w in ln["words"]]

NUM_FIX = {"·": ".", "．": ".", "，": ".", ",": ".", "。": ".", " ": "",
           "L": "1", "l": "1", "丿": "1", "I": "1", "丨": "1", "O": "0",
           "o": "0", "Q": "0", "S": "5", "s": "5", "B": "8", "巧": "15",
           "彐": "3", "元": "", "￥": ""}

def fix_num(s):
    raw = "".join(NUM_FIX.get(ch, ch) for ch in s)
    m = re.fullmatch(r"(\d+)\.(\d{1,2})", raw)
    if m:
        return f"{m.group(1)}.{m.group(2):0<2}", True
    d = "".join(re.findall(r"\d", raw))
    if len(d) >= 4:
        return f"{d[:-2]}.{d[-2:]}", True
    if len(d) >= 1:
        return d, True
    return raw, False

def rows_in_band(y0, y1):
    ws = [w for w in words if y0 <= w["y"] + w["h"] / 2 <= y1]
    lines = []
    for w in sorted(ws, key=lambda w: (w["y"] + w["h"] / 2, w["x"])):
        cy = w["y"] + w["h"] / 2
        if lines and abs(cy - lines[-1][0]) < 28:
            lines[-1][1].append(w)
        else:
            lines.append([cy, [w]])
    return [(cy, sorted(ws, key=lambda w: w["x"])) for cy, ws in lines]

def cell(ws, x0, x1):
    return "".join(w["t"].strip() for w in ws if x0 <= w["x"] + w["w"] / 2 < x1)

out_rows = []

# ---- 表B: 定额工日价格 ----
print("== 表B 定额工日价格 (元/工日) ==")
for cy, ws in rows_in_band(1880, 2650):
    seq = cell(ws, 0, 480).strip()
    name = cell(ws, 480, 1050).strip()
    unit = cell(ws, 1050, 1900).strip()
    price_raw = cell(ws, 1900, 99999).strip()
    if not re.fullmatch(r"\d{1,2}", seq) or not price_raw:
        continue
    price, ok = fix_num(price_raw)
    print(f"  {seq} {name} {unit} {price} {'OK' if ok else '待核:' + price_raw}")
    out_rows.append({"表": "定额工日价格", "项目": name, "单位": unit or "工日",
                     "数值": price if ok else "", "原文": price_raw,
                     "备注": "2026年9月 深圳", "页": 101})

# ---- 表A: 定额人工费指数，数字词按x间隙切列 ----
print("\n== 表A 定额人工费指数 (基期2016Q1=100, 取2026年9月列) ==")
FALLBACK = ["普工人工费", "技工人工费", "高级技工人工费"]
fi = 0
for cy, ws in rows_in_band(1200, 1420):
    label = cell(ws, 0, 1050).replace(" ", "")
    m = re.search(r"(高级技工|普工|技工)", label.replace("，", "").replace("、", "").replace("．", "").replace("。", ""))
    if m:
        name = m.group(1) + "人工费"
        fi = FALLBACK.index(name) + 1 if name in FALLBACK else fi
    elif re.match(r"^\d", label) and fi < 3:
        name = FALLBACK[fi]
        fi += 1
    else:
        continue
    nums = [w for w in ws if w["x"] + w["w"] / 2 >= 800 and re.search(r"\d", w["t"])]
    nums.sort(key=lambda w: w["x"])
    groups, cur = [], []
    prev_right = None
    for w in nums:
        if prev_right is not None and w["x"] - prev_right > 20 and cur:
            groups.append(cur)
            cur = []
        cur.append(w)
        prev_right = w["x"] + w["w"]
    if cur:
        groups.append(cur)
    if not groups:
        continue
    last = "".join(w["t"] for w in groups[-1])
    val, ok = fix_num(last)
    allv = []
    for g in groups:
        v, _ = fix_num("".join(w["t"] for w in g))
        allv.append(v)
    print(f"  {name}: 9月={val} {'OK' if ok else '待核'} | 全{len(groups)}列: {' '.join(allv)}")
    out_rows.append({"表": "定额人工费指数", "项目": name, "单位": "指数",
                     "数值": val if ok else "", "原文": last,
                     "备注": "基期2016Q1=100; 全列:" + " ".join(allv), "页": 101})

csv_path = WORK / "2026年9月人工费.csv"
with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["表", "项目", "单位", "数值", "原文", "备注", "页"])
    w.writeheader()
    for r in out_rows:
        w.writerow(r)
print(f"\n-> {csv_path.name}  共{len(out_rows)}行")
