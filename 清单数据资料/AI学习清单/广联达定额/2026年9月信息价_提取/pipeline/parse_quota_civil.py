# -*- coding: utf-8 -*-
"""土建册单列版式解析器（建筑/装配式/土石方 费用参考价版式）。

与安装/市政三列消耗量版式不同，土建册每页结构（SJG 2024）：
  上区 费用构成表：左表头列 + N 个子目列并排（N=1~3），纵向行 =
    子目编号 / 子目名称 / 2023年8月全费用参考综合单价 / 2023年8月参考综合单价 /
    其中-人工费/材料费/机械费 / 管理费/利润/安全文明施工措施费/规费/税金
  下区 消耗量表：工料机名称 | 单位 | N 列 (消耗量|基期价) 并排，
    尾三行 = 普工人工费/技工人工费/高级技工人工费（金额）
  编码为 OCR 碎片（如 0102-13 碎成 "1)(2" + "一" + "13"），全书无明文编码锚，
  靠位置先验+字符映射重组（宁缺勿脏：校验不过整组丢弃）。

输出与 parse_quota.py 同构（pages[{file,section,unit,work_content,items[{code,labor,materials,fees,...}]}]），
下游 quota_import.py 直接可用。
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter

# ---------- 字符映射 ----------
# 编码碎片字符 → 数字（形近 OCR 变体）。位语义：头4位=章2+节2，尾1~3位=子目号。
_CH_MAP = {
    "0": "0", "O": "0", "o": "0", "D": "0", "Q": "0", "口": "0", "○": "0",
    "〇": "0", "C": "0", "c": "0", "G": "0", ")": "0", "(": "0", "〔": "0",
    "〕": "0", "之": "0",
    "1": "1", "l": "1", "I": "1", "|": "1", "!": "1", "丿": "1", "」": "1",
    "工": "1", "侦": "1", "/": "1",
    "2": "2", "Z": "2", "z": "2",
    "3": "3", "E": "3", "彐": "3", "刃": "0",  # 刃实测位3(节十位=0)
    "4": "4", "A": "4", "又": "4", "<": "4",
    "5": "5", "S": "5", "s": "5", "丿": "5",
    "6": "6", "b": "6", "G": "6", ")": "6",
    "7": "7", "T": "7", "L": "7", ">": "7", "上": "7",
    "8": "8", "B": "8", "&": "8",
    "9": "9", "g": "9", "q": "9",
    "x": "0", "X": "0", "×": "0",  # × 实测位2/位3（章/节高位=0 族）
    "用": "0", "M": "1", "m": "1", "<": "0", ">": "0",
    "一": "-", "-": "-", "—": "-", "–": "-", "~": "-", "_": "-",
    "=": "-", "·": "-", "．": ".", ".": ".",
}
_SEP = set("一-—–~_=<·")
# 数字词内 OCR 噪声（金额/消耗量重建用）
_NUM_MAP = {
    "O": "0", "o": "0", "D": "0", "Q": "0", "口": "0", "C": "0",
    "l": "1", "I": "1", "|": "1", "L": "1", "L".lower(): "1", "!": "1",
    "上": "5", "S": "5", "s": "5", "巧": "5", "&": "8", "B": "8",
    "與": ".", "，": ".", "、": ".", "．": ".", ".": ".",
    "彐": "3", "之": "2", "<": "", ">": "", " ": "",
    "〕": "", "〔": "", ")": "", "(": "", "(": "",
}
_FEE_LABELS = [
    ("全费用参考综合单价", ("全", "费", "用", "参", "考", "综", "合", "单", "价")),
    ("参考综合单价", ("参", "考", "综", "合", "单", "价")),
    ("人工费", ("人", "工", "费")),
    ("材料费", ("材", "料", "费")),
    ("机械费", ("机", "械", "费")),
    ("管理费", ("管", "理", "费")),
    ("利润", ("利", "润")),
    ("安全文明施工措施费", ("安", "全", "文", "明", "施", "工", "措", "施", "费")),
    ("规费", ("规", "费")),
    ("税金", ("税", "金")),
]
_LABOR_ROWS = ("普工人工费", "技工人工费", "高级技工人工费")
_NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")
# 单位白名单：OCR 碎片常混入单位格（实测 '3'、'匚'）——非白名单单位一律
# 置空走页级兜底/默认值
_UNIT_OK = re.compile(
    r"^(10|100)?(m2|m3|m|㎡|m²|m³|t|kg|g|件|个|套|台|块|根|处|座|组|只|条|"
    r"樘|工日|宗|项|系统|槿|橙|株|丛|m3/|次|车|kwh)$")


def _clean_unit(u):
    u = (u or "").strip()
    return u if u and _UNIT_OK.match(u) else ""


def _cells_of(page):
    """[(y, x, t)] 词级单元。"""
    out = []
    for ln in page.get("lines", []):
        for w in (ln.get("words") or []):
            if isinstance(w, dict) and w.get("t") is not None:
                out.append((int(w["y"]), int(w["x"]), str(w["t"])))
    return out


def _rows_of(cells, tol=8):
    """词按 y 聚行 -> [(y, [(x,t),...])] 按 x 有序。
    一维 gap 切分行：y 排序后相邻词 y 差 > gap 切新行——固定容差会把相邻
    行（表头 y384/编码 y396，差 12）并掉，也会把同行词拆散（同行差可达 8）。"""
    gap = 10
    buckets = []
    for y, x, t in sorted(cells, key=lambda c: (c[0], c[1])):
        if buckets and y - buckets[-1][3] <= gap:
            b = buckets[-1]
            b[1].append((x, t))
            b[0] = (b[0] * (len(b[1]) - 1) + y) / len(b[1])
        else:
            buckets.append([float(y), [(x, t)], 0, y])  # [行心, 词, _, 首词y锚]
    return [(b[0], sorted(b[1])) for b in buckets]


def _num_clean(s):
    """OCR 金额词清洗：映射噪声字符、丢点重插。"""
    raw = "".join(_NUM_MAP.get(ch, ch) for ch in str(s))
    raw = raw.strip()
    if raw in ("", "-", ".", "一"):
        return None
    return raw


def _join_nums(parts):
    """词序列拼数值：['5','305','．','69']->5305.69；['5305．69']->5305.69。
    允许丢点（['5305','69']->5305.69 无法判，返回 None 宁可空）。"""
    s = "".join(parts)
    s = "".join(_NUM_MAP.get(ch, ch) for ch in s)
    s = re.sub(r"[^0-9.\-]", "", s)
    if s.count(".") > 1:
        # 多点：保留最右为小数点，其余删
        i = s.rfind(".")
        s = s[:i].replace(".", "") + s[i:]
    if not s or s in (".", "-", "-."):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v


_ZERO_FAMILY = {"0", "O", "o", "D", "Q", "口", "○", "〇", "C", "c", "G",
                ")", "(", "〔", "〕", "之", "×", "X", "x", "用", "刃", "<", ">"}
_ONE_FAMILY = {"1", "l", "I", "|", "!", "丿", "」", "工", "侦", "M", "m", "/",
               "L", "L".lower(), "一"}
# 头部 4 位 = 章(2)+节(2)；位置先验：土建分册制章号 1-9（位1 恒 0），节多为
# 个位数（位3 多为 0）——同一字符在不同位映射不同（'×'位2→1 / 位3→0），
# 位置相关映射表解决 OCR 多义（dict 单键表无法表达）。
_HEAD_MAP_BY_POS = [
    {**{ch: "0" for ch in _ZERO_FAMILY}, **{ch: "0" for ch in _ONE_FAMILY}},  # 位1=章十位
    {**{ch: "0" for ch in _ZERO_FAMILY}, **{ch: "1" for ch in _ONE_FAMILY},
     "2": "2", "Z": "2", "z": "2", "3": "3", "E": "3", "彐": "3",
     "4": "4", "A": "4", "又": "4", "5": "5", "S": "5", "s": "5",
     "6": "6", "b": "6", "7": "7", "T": "7", "上": "7",
     "8": "8", "B": "8", "&": "8", "9": "9", "g": "9", "q": "9"},  # 位2=章个位
    {**{ch: "0" for ch in _ZERO_FAMILY}, **{ch: "1" for ch in _ONE_FAMILY},
     "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7",
     "8": "8", "9": "9"},  # 位3=节十位
    {**{ch: "0" for ch in _ZERO_FAMILY}, **{ch: "1" for ch in _ONE_FAMILY},
     "2": "2", "Z": "2", "z": "2", "3": "3", "E": "3", "彐": "3",
     "4": "4", "A": "4", "又": "4", "<": "4", "5": "5", "S": "5", "s": "5",
     "6": "6", "b": "6", "G": "6", "7": "7", "T": "7", "L": "7", "上": "7",
     "8": "8", "B": "8", "&": "8", "9": "9", "g": "9", "q": "9"},  # 位4=节个位
]
_TAIL_MAP = {**{ch: "0" for ch in _ZERO_FAMILY}, **{ch: "1" for ch in _ONE_FAMILY},
             "2": "2", "Z": "2", "z": "2", "3": "3", "E": "3", "彐": "3",
             "4": "4", "A": "4", "又": "4", "<": "4", "5": "5", "S": "5",
             "s": "5", "丿": "5", "巧": "5", "6": "6", "b": "6", "G": "6",
             "7": "7", "T": "7", "L": "7", "上": "7", ">": "7",
             "8": "8", "B": "8", "&": "8", "9": "9", "g": "9", "q": "9"}


def _recode(group_chars):
    """编码碎片重组：字符序列 -> (code, conf)。conf: high/drop（宁缺勿脏）。"""
    s = "".join(group_chars)
    sep_i = -1
    for i, ch in enumerate(s):
        if ch in _SEP:
            sep_i = i
            break
    if sep_i < 2:
        return None, "drop"
    head_raw = s[:sep_i]
    tail_raw = s[sep_i + 1:]
    if len(head_raw) != 4 or not tail_raw:
        return None, "drop"
    head = "".join(_HEAD_MAP_BY_POS[i].get(ch, "") for i, ch in enumerate(head_raw))
    tail = "".join(_TAIL_MAP.get(ch, "") for ch in tail_raw if ch not in _SEP)
    if len(head) != 4 or not head.isdigit():
        return None, "drop"
    if not tail.isdigit() or not (1 <= len(tail) <= 3):
        return None, "drop"
    head_v = int(head)
    tail_v = int(tail)
    if not (101 <= head_v <= 909):  # 章 1-9、节 01-99
        return None, "drop"
    if not (1 <= tail_v <= 299):
        return None, "drop"
    return f"{head}-{tail}", "high"


def _x_groups(xs, gap=55):
    """x 坐标聚组：相邻词 x 距 > gap 切开。返回 [(x_min, x_max)]。"""
    if not xs:
        return []
    xs = sorted(xs)
    groups = [[xs[0], xs[0]]]
    for x in xs[1:]:
        if x - groups[-1][1] > gap:
            groups.append([x, x])
        else:
            groups[-1][1] = x
    return [(g[0], g[1]) for g in groups]


def _find_word(cells, ch, x_max=950, y_range=None):
    """找字符词，返回 y 列表。"""
    out = []
    for y, x, t in cells:
        if x >= x_max or t != ch:
            continue
        if y_range and not (y_range[0] <= y <= y_range[1]):
            continue
        out.append(y)
    return out


def parse_page(page, fname, head_str):
    """解析单页 -> dict 或 None。head_str（0+章+节2位）由 main 状态机给出——
    头部碎片字符无法可靠映射章节目真值（'1'是0是1？')'是1是2？全书无明文
    编码锚、节标题 OCR 覆盖不全），main 用"节标题行 + 尾号回退"状态机推断。
    全部词级窗口操作（表头/编码行 y 距仅 4-6px 全局行切分会并行；仅消耗量区
    行距大用行切分）。"""
    cells = _cells_of(page)
    if not cells:
        return None

    # 页类型：词级锚——"编"+"号"（子目编号表头）与"工料机"+"名称"
    ys_bian = _find_word(cells, "编")
    code_hdr_y = None
    for yb in ys_bian:
        if _find_word(cells, "号", y_range=(yb - 4, yb + 4)):
            code_hdr_y = yb
            break
    ys_gong = _find_word(cells, "工", x_max=900)
    mach_hdr_y = None
    for yg in ys_gong:
        if _find_word(cells, "称", x_max=900, y_range=(yg - 4, yg + 4)):
            if _find_word(cells, "料", x_max=900, y_range=(yg - 4, yg + 4)) and \
               _find_word(cells, "名", x_max=900, y_range=(yg - 4, yg + 4)):
                mach_hdr_y = yg
                break
    if code_hdr_y is None or mach_hdr_y is None or mach_hdr_y < code_hdr_y:
        return None

    # 编码行：line.text 已按视觉行聚合（'1)(2一13' 整行）——用行级文本抓
    # "含分隔符+数字"行（x>950，费用区内），比词级窗口稳（版式变体表头与
    # 编码行间距不一，词级 2-24px 窗口会抓到"2023年8月"日期行）。
    code_lines = []
    for ln in page.get("lines", []):
        t = (ln.get("text") or "").replace(" ", "")
        if len(t) > 14 or not any(c in t for c in _SEP) or not any(c.isdigit() for c in t):
            continue
        ws = ln.get("words") or []
        xs = [int(w.get("x", 0)) for w in ws if isinstance(w, dict)]
        if not xs:
            continue
        y0 = min(int(w.get("y", 0)) for w in ws if isinstance(w, dict))
        if min(xs) < 950 or not (code_hdr_y < y0 < mach_hdr_y - 30):
            continue
        code_lines.append((y0, min(xs), max(xs), t))
    if not code_lines:
        return None
    code_lines.sort(key=lambda c: c[1])
    groups = _x_groups([c[1] for c in code_lines], gap=60)
    if not (1 <= len(groups) <= 4):
        return None

    # 编码重组：形态校验（头3~6字符+分隔+1~3位尾），头部取页级章节锚，
    # 尾部字符映射数字。形态不过即丢（宁缺勿脏）。
    items = []
    for gx0, gx1 in groups:
        cand = [c for c in code_lines if gx0 - 10 <= c[1] <= gx1 + 10]
        if not cand:
            continue
        y0, x0, x1, s = sorted(cand, key=lambda c: c[0])[0]
        sep_i = next((i for i, ch in enumerate(s) if ch in _SEP), -1)
        tail_raw = s[sep_i + 1:] if sep_i > 0 else ""
        if sep_i < 3 or not tail_raw:
            continue
        tail = "".join(_TAIL_MAP.get(ch, "") for ch in tail_raw if ch not in _SEP)
        if not tail.isdigit() or not (1 <= int(tail) <= 299):
            continue
        code = f"{head_str}-{int(tail)}"
        if any(it["code"] == code for it in items):
            continue  # 页内重复=碎片撕裂，丢弃后者
        items.append({"code": code, "_g": (x0, x1)})
    if not items:
        return None

    # ---- 费用区标签（词级锚：左表头首字）----
    fee_anchors = {}
    for name, chars in _FEE_LABELS:
        for y0 in _find_word(cells, chars[0], x_max=950):
            if not (code_hdr_y - 30 <= y0 <= mach_hdr_y - 30):
                continue
            sib = "".join(t for y, x, t in cells
                          if abs(y - y0) <= 4 and x < 950)
            if "".join(chars) in sib:
                fee_anchors[name] = y0
                break
    # 名称/单位锚
    name_y = None
    for y0 in _find_word(cells, "名", x_max=950):
        if code_hdr_y < y0 < mach_hdr_y:
            sib = "".join(t for y, x, t in cells if abs(y - y0) <= 4 and x < 950)
            if "子目名称" in sib:
                name_y = y0
                break

    def _gv(g_span, y_center, tol=8):
        parts = [t for y, x, t in cells
                 if abs(y - y_center) <= tol and g_span[0] <= x <= g_span[1]
                 and (any(c.isdigit() for c in t) or t in _SEP or t in _NUM_MAP)]
        return _join_nums(parts)

    for it in items:
        gx0, gx1 = it["_g"]
        g_span = (gx0 - 30, gx1 + 130)
        fees = {}
        for name, y0 in fee_anchors.items():
            v = _gv(g_span, y0)
            if v is not None:
                fees[name] = v
        it["fees"] = fees
        it["name"] = ("".join(t for y, x, t in cells
                      if name_y is not None and abs(y - name_y) <= 6
                      and gx0 - 20 <= x <= gx1 + 45) if name_y else "")
        it["unit"] = ""
        # 单位：费用区"单位"表头词下的组值
        for y0 in _find_word(cells, "单", x_max=950):
            if code_hdr_y < y0 < mach_hdr_y:
                sib = "".join(t for y, x, t in cells if abs(y - y0) <= 4 and x < 950)
                if "单位" in sib:
                    un = "".join(t for y, x, t in cells
                                 if abs(y - y0) <= 6 and gx0 - 20 <= x <= gx1 + 45
                                 and not any(c.isdigit() for c in t))
                    it["unit"] = _clean_unit(un)
                    break

    # ---- 消耗量区（行距 24+，可安全行切分）----
    sec_cells = [(y, x, t) for y, x, t in cells if y > mach_hdr_y + 12]
    sec_rows = _rows_of(sec_cells)
    labor = {k: None for k in ("普工", "技工", "高级技工")}
    materials = {it["code"]: [] for it in items}
    unit_page = ""
    for y, cs in sec_rows:
        name_part = "".join(t for x, t in cs if x < 950).strip()
        if not name_part or "合计" in name_part:
            continue
        matched_labor = None
        # 包含匹配+最长优先：OCR 行名带残字（'工技工人工费'=技工人工费前
        # 多一'工'）；'高级技工人工费'也包含'技工人工费'子串，必须长名先查
        for lab in sorted(_LABOR_ROWS, key=len, reverse=True):
            if lab in name_part.replace(" ", ""):
                matched_labor = lab  # 全名键
                break
        for it in items:
            gx0, gx1 = it["_g"]
            nums = [(x, t) for x, t in cs if gx0 - 45 <= x <= gx1 + 230
                    and (any(c.isdigit() for c in t) or t in _SEP or t in _NUM_MAP)]
            if not nums:
                continue
            nums.sort(key=lambda p: p[0])
            qty = _join_nums([t for x, t in nums if x <= gx1 + 80])
            price = _join_nums([t for x, t in nums if x > gx1 + 80])
            if matched_labor:
                if qty is not None:
                    labor[matched_labor] = qty
            elif qty is not None:
                unit_hint = ""
                for x, t in cs:
                    if 950 <= x < gx0 - 45 and t.strip():
                        unit_hint = _clean_unit(t)
                        break
                if not unit_page and unit_hint:
                    unit_page = unit_hint
                materials[it["code"]].append({
                    "name": name_part, "spec": "", "unit_hint": unit_hint,
                    "qty": qty, "price": price,
                })

    # ---- 页级元数据 ----
    section = ""
    work_content = ""
    for y, x, t in cells:
        if y < code_hdr_y - 20 and x < 900:
            pass
    for y, cs in _rows_of([(y, x, t) for y, x, t in cells if y < code_hdr_y - 6]):
        tx = "".join(t for _, t in cs)
        if re.match(r"^\d", tx) and ("工程" in tx or "安装" in tx or "吊装" in tx):
            if len(tx) >= 4:
                section = tx
                break
    for y, cs in _rows_of([(y, x, t) for y, x, t in cells
                           if code_hdr_y - 40 <= y <= mach_hdr_y]):
        tx = "".join(t for _, t in cs)
        if tx.startswith("工作内容"):
            work_content = tx
            break

    out_items = []
    for it in items:
        lab = dict(labor)
        s = sum(v for v in lab.values() if v is not None)
        fl = it["fees"].get("人工费")
        out_items.append({
            "code": it["code"],
            "name": it["name"],
            "unit": it["unit"] or unit_page,
            "labor": lab,
            "materials": materials.get(it["code"], []),
            "fees": it["fees"],
            "check_labor_sum": round(s, 2) if s else None,
            "check_labor_diff": round(s - fl, 2) if (s and fl is not None) else None,
            "check_ok": bool(s and fl is not None and abs(s - fl) <= max(2.0, fl * 0.02)),
        })

    return {
        "file": fname,
        "section": section,
        "unit": unit_page,
        "work_content": work_content,
        "items": out_items,
    }


def _page_sec_anchor(cells, code_hdr_y):
    """页级节标题扫描 -> (ch, sec, section文本) 或 None。正文章节标题 OCR
    覆盖不全（实测全书仅 1 处命中），缺失页由 main 状态机用尾号回退推断。"""
    ch_no = sec_no = None
    section = ""
    for y, cs in _rows_of([(y, x, t) for y, x, t in cells if y < code_hdr_y - 4]):
        tx = "".join(t for x, t in cs if x < 900)
        m = re.match(r"^(\d)\s*[.、．]?\s*(\d{1,2})\s*[.、．]", tx)
        if m:
            ch_no, sec_no = int(m.group(1)), int(m.group(2))
            section = tx
            break
        m2 = re.match(r"^第\s*([一二三四五六七八九十]+)\s*章", tx)
        if m2:
            cn = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
                  "七": 7, "八": 8, "九": 9, "十": 10}.get(m2.group(1))
            if cn:
                ch_no = cn
                section = tx
            continue
    if ch_no is None or not (1 <= ch_no <= 9):
        return None
    return ch_no, sec_no if sec_no is not None else 0, section


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, help="工作目录（含 json/ 子目录）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    jdir = os.path.join(args.work, "json")
    files = sorted(glob.glob(os.path.join(jdir, "*.json")))
    pages = []
    merged = {}  # code -> item（跨页同 code 合并：材料拼接、labor 取非 None、fees 首次）
    order = []
    n_skip = n_items = 0
    # 章节状态机：初始第1章第1节（装配式实测第一章=1.1 预制混凝土构件安装，
    # page_012 证实）；节标题 OCR 覆盖不全——缺失时用尾号回退（本页最小尾号
    # < 上页最大尾号 = 新节起点，sec+1 重跑该页）。代价：跨章只递增节号
    # （章语义弱化，编码仍唯一稳定；检索按名称为主）。
    ch, sec = 1, 1
    prev_max_tail = 0
    for f in files:
        try:
            page = json.load(open(f, encoding="utf-8-sig"))
        except Exception:
            n_skip += 1
            continue
        cells = _cells_of(page)
        anchor = _page_sec_anchor(cells, 10**9) if cells else None
        if anchor:
            ch, sec = anchor[0], anchor[1]
        head_str = f"0{ch}{sec:02d}"
        r = parse_page(page, os.path.basename(f), head_str)
        if r and r["items"]:
            tails = [int(it["code"].split("-")[1]) for it in r["items"]]
            if (prev_max_tail and tails and min(tails) < prev_max_tail
                    and min(tails) <= 30):
                sec += 1
                head_str = f"0{ch}{sec:02d}"
                r = parse_page(page, os.path.basename(f), head_str)
                if not (r and r["items"]):
                    continue
                tails = [int(it["code"].split("-")[1]) for it in r["items"]]
            prev_max_tail = max(tails)
            r["section"] = anchor[2] if anchor else r["section"]
            pages.append(r)
            for it in r["items"]:
                n_items += 1
                m = merged.get(it["code"])
                if m is None:
                    merged[it["code"]] = it
                    order.append(it["code"])
                else:
                    m["materials"].extend(it["materials"])
                    for k, v in it["labor"].items():
                        if v is not None:
                            m["labor"][k] = v
                    for k, v in it["fees"].items():
                        m["fees"].setdefault(k, v)
                    if not m["name"] and it["name"]:
                        m["name"] = it["name"]
                    if not m["unit"] and it["unit"]:
                        m["unit"] = it["unit"]
        else:
            n_skip += 1
    # 重算勾稽（合并后）
    uniq_items = [merged[c] for c in order]
    for it in uniq_items:
        s = sum(v for v in it["labor"].values() if v is not None)
        fl = it["fees"].get("人工费")
        it["check_labor_sum"] = round(s, 2) if s else None
        it["check_labor_diff"] = round(s - fl, 2) if (s and fl is not None) else None
        it["check_ok"] = bool(s and fl is not None
                             and abs(s - fl) <= max(2.0, fl * 0.02))
    # 输出 pages 结构（同 parse_quota.py）：同 code 只保留首次页且用合并后版本
    seen = set()
    out_pages = []
    for p in pages:
        keep = []
        for it in p["items"]:
            if it["code"] in seen:
                continue
            seen.add(it["code"])
            keep.append(merged[it["code"]])
        if keep:
            q = dict(p)
            q["items"] = keep
            out_pages.append(q)
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(out_pages, fp, ensure_ascii=False, indent=1)
    n_ok = sum(1 for it in uniq_items if it["check_ok"])
    dup = n_items - len(uniq_items)
    print(f"页 {len(pages)}/{len(files)}（跳过 {n_skip}） 子目 {len(uniq_items)}"
          f"（跨页合并 {dup}） 勾稽✓ {n_ok}"
          f"（{100*n_ok/max(1,len(uniq_items)):.0f}%）")


if __name__ == "__main__":
    main()
