# -*- coding: utf-8 -*-
"""解析 Excel 单元格公式（工程量列常用）。"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from openpyxl.utils import column_index_from_string, get_column_letter

_CELL_REF = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)")


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def eval_cell(
    ws,
    row: int,
    col: int,
    cache: Optional[Dict[Tuple[int, int], Optional[float]]] = None,
    depth: int = 0,
) -> Optional[float]:
    """求值 1-based 单元格；支持 =A1+B1 等简单四则运算。"""
    if depth > 12:
        return None
    key = (row, col)
    if cache is not None:
        if key in cache:
            return cache[key]
    val = ws.cell(row, col).value
    if val is None:
        if cache is not None:
            cache[key] = None
        return None
    if isinstance(val, (int, float)):
        out = float(val)
        if cache is not None:
            cache[key] = out
        return out
    s = str(val).strip()
    if not s.startswith("="):
        out = _to_float(s)
        if cache is not None:
            cache[key] = out
        return out
    out = _eval_expr(ws, s[1:].replace(" ", ""), row, col, cache, depth + 1)
    if cache is not None:
        cache[key] = out
    return out


def _eval_expr(
    ws,
    expr: str,
    row: int,
    col: int,
    cache: Optional[Dict[Tuple[int, int], Optional[float]]],
    depth: int,
) -> Optional[float]:
    if not expr:
        return None

    def repl(m: re.Match) -> str:
        c = column_index_from_string(m.group(1))
        r = int(m.group(2))
        v = eval_cell(ws, r, c, cache, depth)
        return str(v if v is not None else "nan")

    replaced = _CELL_REF.sub(repl, expr)
    if "nan" in replaced:
        return None
    if not re.match(r"^[\d.+\-*/()]+$", replaced):
        return None
    try:
        return float(eval(replaced))  # noqa: S307 — trusted local xlsx
    except Exception:
        return None


def row_quantity_from_ws(
    ws,
    row: int,
    column_map: dict,
    floor_cols=None,
) -> Optional[float]:
    """结合公式求值读取合计/分层工程量。"""
    cache: Dict[Tuple[int, int], Optional[float]] = {}
    qty_i = column_map.get("quantity")
    if qty_i is not None:
        v = eval_cell(ws, row, qty_i + 1, cache)
        if v is not None:
            return v
    if floor_cols:
        total = 0.0
        found = False
        for idx, _ in floor_cols:
            v = eval_cell(ws, row, idx + 1, cache)
            if v is not None:
                total += v
                found = True
        return total if found else None
    return None
