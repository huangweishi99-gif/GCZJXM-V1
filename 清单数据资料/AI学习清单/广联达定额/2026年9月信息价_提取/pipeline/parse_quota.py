"""装饰定额消耗量子目解析 v2: 词级编码锚定 + 消耗量/单价列切分 + 勾稽校验。
版式(实测 page_040):
  行0  "3·塑钢窗" 章节名
  行1  "工作内容:...单位:100m2"
  行2  "020001@1191 一@1303 50@1323 | 020001@1395 一@1507 51@1527 | ..."  <- 编码词级三联
  行8+ 费用构成块(参考综合单价/材料费/管理费... 数值按编码列对齐)
  行23 "工料机名称 单位 人工费及材料、机械消耗量构成"
  行24+ 普工/技工/高级技工人 工费 + 材料行(名称+规格+单位+各列消耗量+单价@x>1960)
用法: python parse_quota.py --work <dir> [--pages 40,120] [--all] [--out x.json]
"""
import argparse
import json
import re
from pathlib import Path

CHAR_FIX = {
    "L": "1", "l": "1", "I": "1", "|": "1", "丿": "1", "厶": "2",
    "彐": "3", "匚": "7", "巧": "5", "&": "8", "＆": "8",
    "·": ".", "．": ".", "。": ".", "，": ".", "曰": "0", "O": "0", "o": "0",
}
FEE_KEYS = ["全费用参考综合单价", "参考综合单价", "人工费", "材料费", "机械费",
            "管理费", "利润", "安全文明施工措施费", "规费", "税金"]
UNIT_WORDS = {"元", "工日", "台班", "m2", "m3", "m", "㎡", "kg", "t", "块", "m2.", "100m2"}


def clean_num(s):
    for a, b in CHAR_FIX.items():
        s = s.replace(a, b)
    s = re.sub(r"[^0-9.,\-]", "", s)
    parts = s.split(".")
    if len(parts) > 2:
        s = "".join(parts[:-1]) + "." + parts[-1]
    if s in ("", ".", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_rows(jf):
    data = json.loads(jf.read_text(encoding="utf-8-sig"))
    words = [w for ln in data["lines"] for w in ln["words"]]
    rows = []
    for w in sorted(words, key=lambda w: (w["y"] + w["h"] / 2, w["x"])):
        cy = w["y"] + w["h"] / 2
        if rows and abs(cy - rows[-1][0]) < 28:
            rows[-1][1].append(w)
        else:
            rows.append([cy, [w]])
    for _, ws in rows:
        ws.sort(key=lambda w: w["x"])
    return rows


NOISE_ONLY = re.compile(r"^[丿LIl|兀元匚]+$")


def is_numish(t):
    return (bool(re.search(r"[\dLIl|丿彐匚巧&＆·．。，曰OoH]", t))
            and not re.search(r"[一-鿿]", t)
            and not NOISE_ONLY.match(t))


def parse_amount(s):
    """金额类解析: 对 OCR 丢小数点恢复。原词串无小数点字符且值异常大时 /100。
    labor 类(单个子目100m2量级千元内)阈值激进; fee 类保守(万元级存在真实值)。"""
    had_dot = "." in s
    v = clean_num(s)
    if v is None:
        return None
    if (not had_dot) and (v > 10000 or (v > 1000 and v == int(v))):
        return v / 100
    return v


def parse_page(jf):
    rows = load_rows(jf)

    # ---- 1. 词级编码锚定: "020001" + "一" + "dd" 三连 ----
    anchors = []  # (code, x_center, row_idx)
    unit = ""
    for ci, (cy, ws) in enumerate(rows):
        txt = "".join(w["t"] for w in ws)
        if "单位" in txt and "：" in txt.replace(" ", ""):
            m = re.search(r"单位：\s*([0-9A-Za-z㎡²m³]*(?:系统|[台个套组根只块条处吨])?)", txt.replace(" ", ""))
            if m and not unit:
                unit = m.group(1)
        for i in range(len(ws) - 2):
            a, b, c = ws[i], ws[i + 1], ws[i + 2]
            if (re.fullmatch(r"0\d{5}", a["t"]) and
                    re.fullmatch(r"[一一—―–\-]", b["t"]) and
                    re.fullmatch(r"\d{2,3}", c["t"])):
                code = f"{a['t']}-{c['t']}"
                xc = (a["x"] + c["x"] + c["w"]) / 2
                anchors.append({"code": code, "x": xc, "row": ci})
    if not anchors:
        return None
    n = len(anchors)
    r0 = anchors[0]["row"]

    # ---- 2. 章节名: 编码行前, "数字·名称" 形态 ----
    section = ""
    for cy, ws in rows[:r0][::-1]:
        t = "".join(w["t"] for w in ws).replace(" ", "")
        if re.match(r"^\d+\s*[·．.]\s*[^\d·．.]", t) and 3 <= len(t) <= 30 and "说明" not in t:
            section = t
            break
    work = ""
    for cy, ws in rows:
        t = "".join(w["t"] for w in ws).replace(" ", "")
        if t.startswith("工作内容"):
            work = t
            break

    # ---- 3. 列边界 ----
    bounds = []
    for i in range(n):
        lo = anchors[0]["x"] - 220 if i == 0 else (anchors[i - 1]["x"] + anchors[i]["x"]) / 2
        hi = anchors[i]["x"] + 400 if i == n - 1 else (anchors[i]["x"] + anchors[i + 1]["x"]) / 2
        bounds.append((lo, hi))

    items = [{"code": a["code"], "labor": {}, "materials": [], "fees": {}} for a in anchors]

    def col_values(ws):
        """返回 n 列的数值串(列内词按x拼接) + 尾列(单价) 串。
        数值起点 = 首锚-60(排除单位符号"2"/"丿L"等); 尾列起点 = 末锚+150。"""
        per = [[] for _ in range(n)]
        tail = []
        x_start = anchors[0]["x"] - 60
        tail_x = anchors[-1]["x"] + 150
        for w in ws:
            t = w["t"]
            if not is_numish(t):
                continue
            xc = w["x"] + w["w"] / 2
            if xc < x_start:
                continue
            if xc >= tail_x:
                tail.append((w["x"], t))
                continue
            for i, (lo, hi) in enumerate(bounds):
                if lo <= xc < hi:
                    per[i].append((w["x"], t))
                    break
        cols = []
        for i in range(n):
            per[i].sort()
            cols.append("".join(t for _, t in per[i]))
        tail.sort()
        return cols, "".join(t for _, t in tail)

    # ---- 4. 从编码行向下扫 ----
    for cy, ws in rows[r0 + 1:]:
        txt = "".join(w["t"] for w in ws).replace(" ", "")
        if not txt:
            continue
        cols, tail = col_values(ws)

        # 费用/人工关键词行
        hit = None
        if "高级技工人 工费" in txt.replace(" ", "") or ("高级技工" in txt and "人工费" in txt):
            hit = ("labor", "高级技工")
        elif "技工人 工费" in txt.replace(" ", "") or ("技工" in txt and "人工费" in txt):
            hit = ("labor", "技工")
        elif "普工" in txt and "人工费" in txt:
            hit = ("labor", "普工")
        else:
            for key in FEE_KEYS:
                if key in txt:
                    hit = ("fee", key)
                    break
        if hit:
            for i, s in enumerate(cols):
                v = parse_amount(s)
                if v is not None:
                    if hit[0] == "labor":
                        items[i]["labor"][hit[1]] = v
                    else:
                        items[i]["fees"][hit[1]] = v
            continue

        # 材料/机械行: 名称词(x < 首锚-220) 有中文 + 列内有数值
        name_words = [w for w in ws if w["x"] + w["w"] / 2 < bounds[0][0]]
        name = "".join(w["t"] for w in name_words).strip()
        has_cn = any("一" <= ch <= "鿿" for ch in name)
        qtys = {}
        for i, s in enumerate(cols):
            v = clean_num(s)
            if v is not None:
                qtys[items[i]["code"]] = v
        price = clean_num(tail)
        if has_cn and len(name) >= 2 and qtys and "人工费" not in name and "费用" not in name:
            # 拆名称与规格: 末尾拉丁/数字段为规格
            m = re.match(r"^(.*?)([A-Za-z0-9（）().×xX*/\-]+[A-Za-z0-9）)])$", name)
            spec = m.group(2) if m else ""
            nm = m.group(1) if m else name
            if not any("一" <= ch <= "鿿" for ch in nm):
                nm, spec = name, ""
            unit_w = ""
            for w in ws:
                if bounds[0][0] <= w["x"] < anchors[0]["x"] - 20 and not is_numish(w["t"]):
                    if w["t"] in UNIT_WORDS or len(w["t"]) <= 3:
                        unit_w = w["t"]
                        break
            for code, q in qtys.items():
                for it in items:
                    if it["code"] == code:
                        it["materials"].append({"name": nm, "spec": spec, "unit_hint": unit_w,
                                                "qty": q, "price": price})
                        break

    page = {"file": jf.name, "section": section, "unit": unit,
            "work_content": work, "items": items}
    for it in items:
        s = sum(it["labor"].values())
        f = it["fees"].get("人工费")
        if s and f:
            it["check_labor_sum"] = round(s, 2)
            it["check_labor_diff"] = round(s - f, 2)
            it["check_ok"] = abs(s - f) <= max(3.0, f * 0.015)
    return page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--pages", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    json_root = Path(a.work) / "json"
    files = ([json_root / f"page_{int(p):03d}.json" for p in a.pages.split(",")]
             if a.pages else sorted(json_root.glob("*.json")))
    pages = []
    for jf in files:
        if jf.exists():
            p = parse_page(jf)
            if p:
                pages.append(p)
    n_items = sum(len(p["items"]) for p in pages)
    n_ok = sum(1 for p in pages for it in p["items"] if it.get("check_ok"))
    print(f"子目表页 {len(pages)}/{len(files)} | 子目 {n_items} | 勾稽通过 {n_ok}")
    for p in pages[:5]:
        print(f"\n== {p['file']} [{p['section']}] 单位={p['unit']} ×{len(p['items'])}")
        for it in p["items"]:
            mats = "; ".join(f"{m['name'][:8]}{m['spec'][:8]}×{m['qty']}" + (f"@{m['price']}" if m['price'] else "")
                             for m in it["materials"][:3])
            ck = f"勾稽{'✓' if it.get('check_ok') else '✗' + str(it.get('check_labor_diff'))}"
            lab = it["labor"]
            print(f"  {it['code']} {lab} 费{it['fees'].get('人工费')} {ck} | {mats[:75]}")
    if a.out and pages:
        Path(a.out).write_text(json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n已写 {a.out}")


if __name__ == "__main__":
    main()
