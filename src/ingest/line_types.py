"""清单解析共用数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

import pandas as pd

from src.ingest.detector import SheetLayout


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


def cell_str(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def to_float(v: Any) -> Optional[float]:
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
