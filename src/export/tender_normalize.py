# -*- coding: utf-8 -*-
"""甲方招标清单 → 标准成本分析格式（整理后清单）。

格式基准：用户手工整理的『拆除工程-整理清单.xls』（见 docs/清单整理格式.md）。
做法是**在模板副本上改写数据**，不重新绘制样式，因此打印设置、字号、合并、
边框、数字格式与模板 100% 一致。

甲方原始清单结构（xxxx 年为「工程项目招标控制价/投标价汇总表」系列）：
  表02  单项工程汇总
  表04  单位工程汇总 —— 措施项目费 / 规费 / 应纳税费 / 含税造价
  表08A 分部分项工程量清单与计价表（多页、每页重复表头）—— 清单项来源
  表10  措施项目清单与计价汇总表

整理后：单 sheet，A-I 甲方列 + K-Q 成本区 + R-S 价格对比，4 行表头 + N 行数据 + 6 行汇总。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

import xlrd

TEMPLATE_PATH = Path(__file__).parent / "templates" / "tender_normalize_template.xls"

# 表08A 列（0-based）
C_SEQ, C_CODE, C_NAME, C_FEATURE, C_BLANK, C_UNIT, C_QTY, C_UPRICE, C_AMT, C_TMP = range(10)

HEADER_ROWS = 4      # 标题 + 工程名称 + 表头两行
SUMMARY_ROWS = 6     # 分部分项 / 措施 / 规费 / 不含税 / 应纳税 / 含税

# 表08A 里需要跳过的小计类名称
_SMALLTOTAL = ("本页小计", "分部小计", "合    计", "合计", "小计")


@dataclass
class ItemRow:
    """一条清单项。"""

    seq: str
    code: str
    name: str
    feature: str
    unit: str
    qty: Optional[float]
    unit_price: Optional[float]
    amount: Optional[float]


@dataclass
class SectionRow:
    """分部/子分部标题行（如『室内拆除工程』）。"""

    name: str


@dataclass
class TenderSheet:
    """从甲方原始清单解析出的数据。"""

    project_name: str = ""
    short_name: str = ""
    rows: List[Union[SectionRow, ItemRow]] = field(default_factory=list)
    summary: Dict[str, Optional[float]] = field(default_factory=dict)

    @property
    def item_rows(self) -> List[int]:
        """返回 rows 中所有清单项的下标。"""
        return [i for i, r in enumerate(self.rows) if isinstance(r, ItemRow)]


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        v = int(v) if v == int(v) else v
    return str(v).strip()


def _f(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _find_sheet(book: xlrd.Book, *keys: str):
    """按关键字找 sheet。"""
    for name in book.sheet_names():
        if all(k in name for k in keys):
            return book.sheet_by_name(name)
    return None


def _pick_sheet_08a(book: xlrd.Book):
    """找『分部分项工程量清单与计价表』sheet。"""
    for name in book.sheet_names():
        if "08A" in name or "分部分项" in name:
            return book.sheet_by_name(name)
    return None


def _pick_sheet_04(book: xlrd.Book):
    """找『单位工程...汇总表』sheet。"""
    for name in book.sheet_names():
        if ("04" in name or "单位工程" in name) and "汇总" in name:
            return book.sheet_by_name(name)
    return None


def parse_tender(path: str | Path) -> TenderSheet:
    """解析甲方原始清单 xls，返回结构化数据。"""
    path = str(path)
    book = xlrd.open_workbook(path)
    result = TenderSheet()

    # ---------- 工程名称 ----------
    sh08 = _pick_sheet_08a(book)
    if sh08 is None:
        raise ValueError(f"未找到『分部分项工程量清单与计价表』sheet：{path}")
    for r in range(sh08.nrows):
        v = _s(sh08.cell_value(r, 0))
        if v.startswith("工程名称"):
            result.project_name = v.replace("工程名称", "", 1).lstrip(":：").strip()
            break
    # 工程名称分隔符可能是连字符(-)、破折号(—/–)或全角冒号(：)，取最后一段为简称
    for sep in ("-", "—", "–", "："):
        if sep in result.project_name:
            result.short_name = result.project_name.rsplit(sep, 1)[-1].strip()
            break
    else:
        result.short_name = result.project_name

    # ---------- 清单项（表08A，多页重复表头） ----------
    rows: List[Union[SectionRow, ItemRow]] = []
    r = 0
    n = sh08.nrows
    while r < n:
        a = _s(sh08.cell_value(r, C_SEQ))
        b = _s(sh08.cell_value(r, C_CODE))
        c = _s(sh08.cell_value(r, C_NAME))

        # 每页开头的标题块（标题/空/工程名称/表头1/表头2）
        if a.startswith("分部分项工程量清单"):
            r += HEADER_ROWS + 1
            continue
        # 空行
        if not a and not b and not c:
            r += 1
            continue
        # 小计/合计
        if any(k in c for k in _SMALLTOTAL) or any(k in a for k in _SMALLTOTAL):
            r += 1
            continue
        # 清单项：序号 + 编码
        if a and b:
            rows.append(
                ItemRow(
                    seq=a,
                    code=b,
                    name=c,
                    feature=_s(sh08.cell_value(r, C_FEATURE)),
                    unit=_s(sh08.cell_value(r, C_UNIT)),
                    qty=_f(sh08.cell_value(r, C_QTY)),
                    unit_price=_f(sh08.cell_value(r, C_UPRICE)),
                    amount=_f(sh08.cell_value(r, C_AMT)),
                )
            )
            r += 1
            continue
        # 分部标题：仅名称列有值
        if c:
            rows.append(SectionRow(name=c))
            r += 1
            continue
        r += 1
    result.rows = rows

    # ---------- 汇总口径（表04） ----------
    sh04 = _pick_sheet_04(book)
    summary: Dict[str, Optional[float]] = {}
    if sh04 is not None:
        for i in range(sh04.nrows):
            label = _s(sh04.cell_value(i, 1))  # 汇总内容列
            if not label:
                continue
            # 金额列：取该行最右侧的数值列
            amt = None
            for j in range(sh04.ncols - 1, 1, -1):
                val = _f(sh04.cell_value(i, j))
                if val is not None:
                    amt = val
                    break
            for key in ("分部分项工程费", "措施项目费", "规费", "应纳税费",
                        "不含税建安工程造价", "含税建安工程造价"):
                if label == key or label.startswith(key):
                    summary.setdefault(key, amt)
    result.summary = summary
    return result


# ==========================================================================
# 输出：基于模板改写
# ==========================================================================

# 列布局
_COL = {
    "seq": 1, "code": 2, "name": 3, "feature": 4, "unit": 5, "qty": 6,
    "unit_price": 7, "amount": 8, "remark": 9,
    "cost_unit": 11, "main_mat": 12, "loss": 13, "labor": 14,
    "aux": 15, "machine": 16, "cost_total": 17,
    "diff_unit": 18, "diff_total": 19,
}
# 打印区域只到备注列
_LAST_PRINT_COL = 9


def build_xls(data: TenderSheet, out_path: str | Path,
              template: str | Path = TEMPLATE_PATH) -> Path:
    """基于模板生成整理后清单。返回输出文件路径。"""
    try:
        import win32com.client as wc
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("需要 pywin32 + Microsoft Excel 才能写出保留格式的 xls") from e

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    template = Path(template)
    if not template.exists():
        raise FileNotFoundError(f"模板不存在：{template}")

    app = wc.Dispatch("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    try:
        wb = app.Workbooks.Open(str(template))
        ws = wb.Worksheets(1)

        prev_vision = ws.Name  # 模板 sheet 名，最后会改成工程简称

        # ---------- 行数调整 ----------
        used_last = ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1
        tmpl_data_rows = used_last - HEADER_ROWS - SUMMARY_ROWS
        want_data_rows = len(data.rows)

        first_data = HEADER_ROWS + 1  # 数据区首行
        if want_data_rows < tmpl_data_rows:
            # 删掉数据区底部多余的行（自下而上，保住样本行）
            for _ in range(tmpl_data_rows - want_data_rows):
                last_data = HEADER_ROWS + (ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1
                                           - HEADER_ROWS - SUMMARY_ROWS) - 0
                ws.Rows(last_data).Delete()
        elif want_data_rows > tmpl_data_rows:
            # 在数据区底部插行：以最后一行数据为格式样本
            sample = first_data + tmpl_data_rows - 1
            for _ in range(want_data_rows - tmpl_data_rows):
                ws.Rows(sample + 1).Insert()
                ws.Rows(sample).Copy()
                ws.Rows(sample + 1).PasteSpecial(Paste=-4122)  # xlPasteFormats
                app.CutCopyMode = False

        data_last = HEADER_ROWS + want_data_rows
        summary_first = data_last + 1
        last_row = summary_first + SUMMARY_ROWS - 1

        # ---------- 逐行写数据 ----------
        # 先确定模板里的角色样本行（依据模板原有内容：A+B 都有值是清单项，否则是分部）
        sec_sample = None
        item_sample = None
        for i in range(first_data, used_last - SUMMARY_ROWS + 1):
            a = ws.Cells(i, _COL["seq"]).Value
            b = ws.Cells(i, _COL["code"]).Value
            if a not in (None, "") and b not in (None, ""):
                if item_sample is None:
                    item_sample = i
            elif sec_sample is None:
                sec_sample = i
            if sec_sample and item_sample:
                break
        sec_sample = sec_sample or first_data
        item_sample = item_sample or (first_data + 1 if want_data_rows > 1 else first_data)

        # 样本行格式先备份到远处行，循环里只从备份复制。
        # 不能直接用 sec_sample/item_sample 当 Copy 源：目标行可能与样本行重合
        # （如数据区前两行都是分部时，第二轮就会把分部格式贴到 item_sample 行，
        #   此后所有清单项行继承被污染的样本，A/B 列丢失 @ 文本格式，
        #   项目编码 011102003001 被转成浮点 11102003001.0、前导零丢失）。
        FAR_SEC, FAR_ITEM = 600, 601
        ws.Rows(sec_sample).Copy()
        ws.Rows(FAR_SEC).PasteSpecial(Paste=-4122)
        ws.Rows(item_sample).Copy()
        ws.Rows(FAR_ITEM).PasteSpecial(Paste=-4122)
        app.CutCopyMode = False

        for idx, row in enumerate(data.rows):
            r = first_data + idx
            # 按角色从干净备份贴格式。
            # 只有当「模板原角色 == 本次写入角色」时才跳过：
            # r==sec_sample 写分部、r==item_sample 写清单项 → 格式本就正确，不贴；
            # 其余（含样本行角色被改）一律从备份贴，防止模板残留格式错位。
            if isinstance(row, SectionRow):
                skip = (r == sec_sample)
                far = FAR_SEC
            else:
                skip = (r == item_sample)
                far = FAR_ITEM
            if not skip:
                ws.Rows(far).Copy()
                ws.Rows(r).PasteSpecial(Paste=-4122)
                app.CutCopyMode = False
            # 清掉该行旧值（模板残留数据）
            ws.Range(ws.Cells(r, 1), ws.Cells(r, _COL["diff_total"])).ClearContents()
            if isinstance(row, SectionRow):
                # 分部行只写名称：成本区保持黑体空表，不带公式。
                # （用户手工模板里第二个分部行有公式且装配列变成宋体，属复制残留，
                #   这里以首个分部行为准，保证全表自洽。）
                ws.Cells(r, _COL["name"]).Value = row.name
            else:
                ws.Cells(r, _COL["seq"]).Value = row.seq
                ws.Cells(r, _COL["code"]).Value = row.code
                ws.Cells(r, _COL["name"]).Value = row.name
                ws.Cells(r, _COL["feature"]).Value = row.feature
                ws.Cells(r, _COL["unit"]).Value = row.unit
                if row.qty is not None:
                    ws.Cells(r, _COL["qty"]).Value = row.qty
                if row.unit_price is not None:
                    ws.Cells(r, _COL["unit_price"]).Value = row.unit_price
                if row.amount is not None:
                    ws.Cells(r, _COL["amount"]).Value = row.amount
                # 成本区公式（相对引用，同行自算）
                ws.Cells(r, _COL["cost_unit"]).Formula = f"=L{r}*(1+M{r})+N{r}+O{r}+P{r}"
                ws.Cells(r, _COL["cost_total"]).Formula = f"=K{r}*F{r}"
                ws.Cells(r, _COL["diff_unit"]).Formula = f"=K{r}-G{r}"
                ws.Cells(r, _COL["diff_total"]).Formula = f"=Q{r}-H{r}"

        # 清理样本备份行（必须在汇总区/打印区域设置前，否则污染 UsedRange）
        ws.Range(f"{FAR_SEC}:{FAR_ITEM}").Delete()

        # ---------- 汇总区 ----------
        ws.Range(ws.Cells(summary_first, 1), ws.Cells(last_row, _COL["diff_total"])).ClearContents()
        labels = ("分部分项工程费", "措施项目费", "规费",
                  "不含税建安工程造价", "应纳税费", "含税建安工程造价")
        # 这几行的金额是固定值（来自原清单表04），不能做成公式
        fixed = {1: "措施项目费", 2: "规费", 4: "应纳税费"}
        for k, label in enumerate(labels):
            r = summary_first + k
            ws.Cells(r, _COL["name"]).Value = label
            if k in fixed:
                key = fixed[k]
                v = data.summary.get(key)
                if v is not None:
                    ws.Cells(r, _COL["amount"]).Value = v
        # 分部分项工程费：报价合计 / 成本合计均对数据区整体求和（起点含分部行，与模板一致）
        if want_data_rows:
            ws.Cells(summary_first, _COL["amount"]).Formula = f"=SUM(H{first_data}:H{data_last})"
            ws.Cells(summary_first, _COL["cost_total"]).Formula = f"=SUM(Q{first_data}:Q{data_last})"
            ws.Cells(summary_first, _COL["cost_unit"]).Formula = (
                f"=L{summary_first}*(1+M{summary_first})+N{summary_first}"
                f"+O{summary_first}+P{summary_first}"
            )
        # 应纳税费率（D 列 9%）
        ws.Cells(summary_first + 4, _COL["feature"]).Value = 0.09
        ws.Cells(summary_first + 4, _COL["feature"]).NumberFormat = "0.00%"
        # 不含税 = 分部分项 + 措施 + 规费
        ws.Cells(summary_first + 3, _COL["amount"]).Formula = \
            f"=H{summary_first}+H{summary_first+1}+H{summary_first+2}"
        ws.Cells(summary_first + 3, _COL["cost_total"]).Formula = \
            f"=Q{summary_first}+Q{summary_first+1}+Q{summary_first+2}"
        # 应纳税 = 成本不含税 × 费率
        ws.Cells(summary_first + 4, _COL["cost_total"]).Formula = \
            f"=Q{summary_first+3}*D{summary_first+4}"
        # 含税
        ws.Cells(summary_first + 5, _COL["amount"]).Formula = \
            f"=H{summary_first+3}+H{summary_first+4}"
        ws.Cells(summary_first + 5, _COL["cost_total"]).Formula = \
            f"=Q{summary_first+3}+Q{summary_first+4}"
        # 相差列（各行统一 = 成本合计 - 报价合计）
        for k in range(SUMMARY_ROWS):
            r = summary_first + k
            ws.Cells(r, _COL["diff_total"]).Formula = f"=Q{r}-H{r}"

        # ---------- 标题信息 ----------
        ws.Cells(2, 1).Value = f"工程名称:{data.project_name}"
        ws.Cells(1, 1).Value = "分部分项工程量清单与计价表"

        # ---------- 打印 / 其它 ----------
        ws.PageSetup.PrintArea = f"$A$1:$I${last_row}"
        ws.PageSetup.PrintTitleRows = "$1:$4"
        ws.PageSetup.Zoom = 94
        ws.PageSetup.HeaderMargin = 0
        ws.PageSetup.FooterMargin = 14.15
        ws.Name = _safe_sheet_name(data.short_name or prev_vision)

        wb.SaveAs(str(out_path), FileFormat=56)  # 56 = xlExcel8 (.xls)
        wb.Close(False)
    finally:
        app.Quit()
    return out_path


def _safe_sheet_name(name: str) -> str:
    bad = '[]:*?/\\'
    for ch in bad:
        name = name.replace(ch, "_")
    return name[:31] or "Sheet1"


def build_tender(src_xls: str | Path, out_xls: str | Path,
                 template: str | Path = TEMPLATE_PATH) -> Path:
    """解析甲方原始清单并生成整理后清单。"""
    data = parse_tender(src_xls)
    return build_xls(data, out_xls, template=template)
