"""Excel 清单解析：智能表头识别 + 仅解析需报价行。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pandas as pd

from src.ingest.detector import (
    SheetLayout,
    detect_sheet_layout,
    is_pricing_row,
    should_skip_sheet,
)


@dataclass
class ParsedLine:
    sheet_name: str
    section_path: str
    seq: str
    list_code: str
    name: str
    feature: str
    unit: str
    quantity: Optional[float]
    unit_price: Optional[float]
    amount: Optional[float]
    remark: str
    material_main: Optional[float] = None
    material_loss_rate: Optional[float] = None
    material_aux: Optional[float] = None
    labor: Optional[float] = None
    machinery: Optional[float] = None
    management: Optional[float] = None
    profit: Optional[float] = None
    tax: Optional[float] = None
    cost_unit_price: Optional[float] = None
    cost_amount: Optional[float] = None
    row_index: int = 0
    has_cost_detail: bool = False


@dataclass
class ParsedWorkbook:
    file_path: str
    project_name: str
    sheets: List[str]
    lines: List[ParsedLine] = field(default_factory=list)
    format_hint: str = "unknown"
    layouts: List[SheetLayout] = field(default_factory=list)


def _cell_str(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _to_float(v: Any) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        s = str(v).strip().replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None


def _get(row: Tuple[Any, ...], mapping: dict, key: str, alt: Optional[str] = None) -> Any:
    idx = mapping.get(alt or key)
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def _parse_sheet(df: pd.DataFrame, sheet_name: str) -> Tuple[List[ParsedLine], Optional[SheetLayout]]:
    layout = detect_sheet_layout(df, sheet_name)
    if layout is None:
        return [], None

    lines: List[ParsedLine] = []
    section_stack: List[str] = []
    m = layout.column_map

    for i in range(layout.data_start_row, len(df)):
        row = tuple(df.iloc[i].tolist())

        if not is_pricing_row(row, m):
            name = _cell_str(_get(row, m, "name"))
            unit = _cell_str(_get(row, m, "unit"))
            if name and not unit:
                section_stack.append(name)
            continue

        def col(key: str, alt: Optional[str] = None) -> Optional[float]:
            return _to_float(_get(row, m, key, alt))

        mm = col("material_main")
        if m.get("_cost_side"):
            mm = _to_float(_get(row, m, "material_main_cost")) or mm
            la = _to_float(_get(row, m, "labor_cost")) or col("labor")
            ma = _to_float(_get(row, m, "material_aux_cost"))
            mc = _to_float(_get(row, m, "machinery_cost"))
            loss = _to_float(_get(row, m, "material_loss_rate_cost")) or col(
                "material_loss_rate"
            )
            cost_up = _to_float(_get(row, m, "cost_unit_price"))
        else:
            la = col("labor")
            ma = col("material_aux")
            mc = col("machinery")
            loss = col("material_loss_rate")
            cost_up = col("cost_unit_price")
        if cost_up is None and any(x is not None for x in (mm, la, ma, mc)):
            cost_up = (mm or 0) * (1 + (loss or 0)) + (la or 0) + (ma or 0) + (mc or 0)

        feat = _cell_str(_get(row, m, "feature"))
        spec = _cell_str(_get(row, m, "spec")) if "spec" in m else ""
        if spec:
            feat = f"{feat}；规格：{spec}" if feat else f"规格：{spec}"
        if sheet_name and feat and not feat.startswith("["):
            feat = f"[{sheet_name}] {feat}"

        qty = col("quantity")
        cost_amt = col("cost_amount")
        if cost_amt is None and cost_up is not None and qty is not None:
            cost_amt = round(cost_up * qty, 2)

        has_cost = cost_up is not None or any(
            x is not None for x in (mm, la, ma, mc, col("management"), col("profit"))
        )

        lines.append(
            ParsedLine(
                sheet_name=sheet_name,
                section_path=" / ".join(section_stack[-4:]),
                seq=_cell_str(_get(row, m, "seq")),
                list_code=_cell_str(_get(row, m, "list_code")),
                name=_cell_str(_get(row, m, "name")),
                feature=feat,
                unit=_cell_str(_get(row, m, "unit")),
                quantity=qty,
                unit_price=col("unit_price"),
                amount=col("amount"),
                remark=_cell_str(_get(row, m, "remark")) if "remark" in m else "",
                material_main=mm,
                material_loss_rate=loss,
                material_aux=ma,
                labor=la,
                machinery=mc,
                management=col("management"),
                profit=col("profit"),
                tax=col("tax"),
                cost_unit_price=cost_up,
                cost_amount=cost_amt,
                row_index=i,
                has_cost_detail=has_cost,
            )
        )
    return lines, layout


def _extract_project_name(xl: pd.ExcelFile, path: Path) -> str:
    for sheet in xl.sheet_names[:4]:
        d = pd.read_excel(xl, sheet_name=sheet, header=None)
        for i in range(min(25, len(d))):
            for j in range(min(8, d.shape[1])):
                v = _cell_str(d.iloc[i, j])
                if v.startswith("工程名称"):
                    rest = _cell_str(d.iloc[i, j + 1]) if j + 1 < d.shape[1] else ""
                    if rest:
                        return rest.replace("：", "").replace(":", "").strip()
                    return v.split("：")[-1].split(":")[-1].strip()
                if "工程名称：" in v or "工程名称:" in v:
                    return re.split(r"工程名称[：:]", v, maxsplit=1)[-1].strip()
    return path.stem


def parse_workbook(path: str | Path) -> ParsedWorkbook:
    path = Path(path)
    xl = pd.ExcelFile(path)
    project_name = _extract_project_name(xl, path)
    all_lines: List[ParsedLine] = []
    layouts: List[SheetLayout] = []

    for sn in xl.sheet_names:
        if should_skip_sheet(sn):
            continue
        df = pd.read_excel(xl, sheet_name=sn, header=None)
        parsed, layout = _parse_sheet(df, sn)
        if layout:
            layouts.append(layout)
        all_lines.extend(parsed)

    cost_lines = sum(1 for ln in all_lines if ln.has_cost_detail)
    if cost_lines > len(all_lines) * 0.3:
        fmt = "internal_cost"
    elif all_lines and cost_lines == 0:
        fmt = "tender"
    else:
        fmt = "mixed"

    return ParsedWorkbook(
        file_path=str(path),
        project_name=project_name or path.stem,
        sheets=list(xl.sheet_names),
        lines=all_lines,
        format_hint=fmt,
        layouts=layouts,
    )
