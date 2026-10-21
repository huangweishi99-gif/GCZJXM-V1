"""boq_rows.py — 清单行表头探测与读取（openpyxl 矩阵与 Excel COM 共用纯矩阵逻辑）。
列探测关键词按成本分析模板 + 常见甲方表头；识别 项目名称/项目特征/计量单位/工程量/成本单价。
"""
NAME_KEYS = ["项目名称", "名称"]
FEAT_KEYS = ["项目特征", "特征"]
UNIT_KEYS = ["计量单位", "单位"]
QTY_KEYS = ["工程量", "数量"]
COST_KEYS = ["成本单价", "单价合计"]

COLMAP = (("name", NAME_KEYS), ("feature", FEAT_KEYS), ("unit", UNIT_KEYS),
          ("qty", QTY_KEYS), ("cost", COST_KEYS))


def _pick(cells, keys, used):
    for i, h in enumerate(cells):
        if i in used or not h:
            continue
        if any(k in h for k in keys):
            used.add(i)
            return i
    return None


def detect_header(rows, max_scan=12):
    """rows: list[list]；返回 (header_idx, cols{name,feature,unit,qty,cost}) 或 None"""
    for r, row in enumerate(rows[:max_scan]):
        cells = [str(c).strip() if c is not None else "" for c in row]
        if not any("名称" in c or "项目特征" in c for c in cells):
            continue
        used, cols = set(), {}
        for key, keys in COLMAP:
            i = _pick(cells, keys, used)
            if i is not None:
                cols[key] = i
        if "name" in cols and len(cols) >= 3:
            return r, cols
    return None


def iter_items(rows, header_idx, cols):
    """返回 [{seq,row_idx,name,feature,unit,qty,cost}]，跳过空行/分部标题/公式行"""
    out, seq = [], 0
    for r, row in enumerate(rows[header_idx + 1:], start=header_idx + 1):
        def g(k):
            i = cols.get(k)
            v = row[i] if i is not None and i < len(row) else None
            return "" if v is None else str(v).strip()
        name = g("name")
        if not name or name.startswith("=") or name.endswith(("：", ":")):
            continue
        seq += 1
        out.append({"seq": seq, "row_idx": r, "name": name, "feature": g("feature"),
                    "unit": g("unit"), "qty": g("qty"), "cost": g("cost")})
    return out


def read_openpyxl(fp):
    """读取 xlsx 全部 sheet 的清单行（只读模式，data_only）"""
    import openpyxl
    items = []
    wb = openpyxl.load_workbook(fp, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            det = detect_header(rows)
            if not det:
                continue
            hi, cols = det
            for it in iter_items(rows, hi, cols):
                it["sheet"] = ws.title
                items.append(it)
    finally:
        wb.close()
    return items


def read_com(fp):
    """Excel COM 读取 + 附带 xl_row/xl_col 写回坐标（1-based）"""
    import win32com.client
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    items = []
    wb = excel.Workbooks.Open(str(fp))
    try:
        for ws in wb.Worksheets:
            used = ws.UsedRange
            vals = used.Value
            if not vals:
                continue
            rows = [list(r) for r in vals]
            base_r, base_c = used.Row, used.Column
            det = detect_header(rows)
            if not det:
                continue
            hi, cols = det
            for it in iter_items(rows, hi, cols):
                it["sheet"] = ws.Name
                it["xl_row"] = base_r + it["row_idx"]
                it["xl_col"] = {k: base_c + v for k, v in cols.items()}
                items.append(it)
    finally:
        wb.Close(False)
        excel.Quit()
    return items


def norm(s):
    """匹配键归一化：去空白 + 单位写法统一（㎡/m²/M2→m2，m³/㎥→m3）"""
    s = "".join(str(s or "").split())
    for a, b in (("㎡", "m2"), ("m²", "m2"), ("ｍ²", "m2"), ("M2", "m2"),
                 ("m³", "m3"), ("㎥", "m3"), ("M3", "m3")):
        s = s.replace(a, b)
    return s
