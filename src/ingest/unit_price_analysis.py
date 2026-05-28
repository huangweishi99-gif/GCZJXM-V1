"""解析「综合单价分析表」块式 Sheet（每项一组材料/人工/机械拆解）。"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

import pandas as pd

from src.ingest.line_types import ParsedLine, cell_str, to_float


def _row_val(row: pd.Series, idx: int) -> Any:
    if idx >= len(row):
        return None
    return row.iloc[idx]


def _parse_meta_row(row: pd.Series) -> Tuple[str, str, str]:
    """从「项目名称：…  单位：… 序号：…」行提取信息。"""
    name, unit, seq = "", "", ""
    for j in range(len(row)):
        v = cell_str(_row_val(row, j))
        if not v:
            continue
        if v.startswith("项目名称") or v.startswith("项目名称：") or v.startswith("项目名称:"):
            name = re.split(r"项目名称[：:]", v, maxsplit=1)[-1].strip()
        elif v in ("单位：", "单位:"):
            unit = cell_str(_row_val(row, j + 1))
        elif v.startswith("单位：") or v.startswith("单位:"):
            unit = re.split(r"单位[：:]", v, maxsplit=1)[-1].strip()
        elif v in ("序号：", "序号:"):
            seq = cell_str(_row_val(row, j + 1))
        elif v.startswith("序号：") or v.startswith("序号:"):
            seq = re.split(r"序号[：:]", v, maxsplit=1)[-1].strip()
    return name, unit, seq


def _is_material_detail_row(c0: str, c1: str) -> bool:
    if not c1 or "小计" in c1:
        return False
    if c0 in ("一", "二", "三", "四", "五", "六", "七"):
        return False
    return bool(re.match(r"^\d+$", c0))


def _composition_feature(parts: List[str], sheet_name: str) -> str:
    body = "；".join(parts[:12])
    if len(parts) > 12:
        body += f"…等{len(parts)}项"
    return f"[{sheet_name}] 组价明细：{body}"


def parse_unit_price_analysis_sheet(
    df: pd.DataFrame,
    sheet_name: str,
) -> List[ParsedLine]:
    """
    块式综合单价分析表 → ParsedLine 列表。
    每块：标题 → 项目信息 → 人材机明细 → 材料/人工/机械小计 → 综合单价。
    """
    lines: List[ParsedLine] = []
    i = 0
    while i < len(df):
        title = cell_str(_row_val(df.iloc[i], 0))
        if "综合单价分析" not in title:
            i += 1
            continue

        if i + 2 >= len(df):
            break
        name, unit, seq = _parse_meta_row(df.iloc[i + 1])
        if not name or not unit:
            i += 1
            continue

        composition: List[str] = []
        material_total: Optional[float] = None
        labor_total: Optional[float] = None
        machinery_total: Optional[float] = None
        management: Optional[float] = None
        profit: Optional[float] = None
        unit_price: Optional[float] = None

        j = i + 3
        while j < len(df):
            row = df.iloc[j]
            c0 = cell_str(_row_val(row, 0))
            c1 = cell_str(_row_val(row, 1))

            if j > i + 3 and "综合单价分析" in c0:
                break

            if "材料费小计" in c1:
                material_total = to_float(_row_val(row, 5))
            elif "人工费小计" in c1:
                labor_total = to_float(_row_val(row, 5))
            elif c0 == "三" and "机械费" in c1:
                machinery_total = to_float(_row_val(row, 5))
            elif c0 == "五" and "管理费" in c1:
                management = to_float(_row_val(row, 5))
            elif c0 == "六" and "利润" in c1:
                profit = to_float(_row_val(row, 5))
            elif "综合单价" in c1 and c0 == "七":
                unit_price = to_float(_row_val(row, 5))
            elif _is_material_detail_row(c0, c1):
                qty = to_float(_row_val(row, 3))
                up = to_float(_row_val(row, 4))
                u = cell_str(_row_val(row, 2))
                if qty is not None and up is not None:
                    composition.append(f"{c1} {qty}{u}@{up}")

            j += 1

        cost_up = unit_price
        if cost_up is None and material_total is not None:
            cost_up = (material_total or 0) + (labor_total or 0) + (machinery_total or 0)

        if not cost_up or cost_up <= 0:
            i = j
            continue

        feature = _composition_feature(composition, sheet_name)
        lines.append(
            ParsedLine(
                sheet_name=sheet_name,
                section_path="综合单价分析",
                seq=seq,
                list_code="",
                name=name,
                feature=feature,
                unit=unit,
                quantity=1.0,
                unit_price=unit_price,
                amount=unit_price,
                remark="来源：综合单价分析表",
                material_main=material_total,
                material_aux=None,
                labor=labor_total,
                machinery=machinery_total,
                management=management,
                profit=profit,
                cost_unit_price=cost_up,
                cost_amount=cost_up,
                row_index=i,
                has_cost_detail=True,
            )
        )
        i = j

    return lines


def enrich_from_boq_features(
    analysis_lines: List[ParsedLine],
    boq_lines: List[ParsedLine],
) -> None:
    """用清单 Sheet 的项目特征补充分析表条目（按名称+序号）。"""
    boq_by_key: dict[Tuple[str, str], str] = {}
    for bl in boq_lines:
        if not bl.feature or bl.feature.startswith("[") and "组价明细" in bl.feature:
            continue
        key = (cell_str(bl.name), cell_str(bl.seq))
        if key[0] and bl.feature:
            boq_by_key[key] = bl.feature
        key2 = (cell_str(bl.name), "")
        if key2[0] and bl.feature and key2 not in boq_by_key:
            boq_by_key[key2] = bl.feature

    for ln in analysis_lines:
        extra = boq_by_key.get((ln.name, ln.seq)) or boq_by_key.get((ln.name, ""))
        if extra and extra not in ln.feature:
            ln.feature = f"{extra}\n{ln.feature}"
