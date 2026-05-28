"""智能识别 Excel 清单表头（列数可变、备注可选、双行表头）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# 字段别名（成本列须在 unit_price 之前，避免「材料成本单价」误匹配「单价」）
FIELD_ALIASES: Dict[str, List[str]] = {
    "seq": ["序号", "项号", "编码序号", "编号"],
    "list_code": ["项目编码", "清单编码", "清单编号"],
    "name": ["项目名称", "分部分项名称", "分部分项", "分区分类描述", "名称", "材料名称"],
    "feature": [
        "项目特征描述",
        "项目特征",
        "特征描述",
        "特征",
        "部位",
        "工作内容",
        "型号及规格",
    ],
    "spec": ["规格"],
    "unit": ["计量单位", "计量\n单位", "单位"],
    "quantity": [
        "24/25年暂估工程量",
        "暂估工程量",
        "成本数量",
        "增加数量",
        "工程数量",
        "工程量",
        "数量",
    ],
    "material_main": [
        "材料成本单价",
        "材料计划成本单价",
        "材料费",
        "主材费",
        "主材",
    ],
    "material_loss_rate": ["主材损耗率", "损耗率"],
    "labor": ["人工成本单价", "人工费", "人工"],
    "material_aux": ["辅材费", "辅材"],
    "machinery": ["机械费", "机械"],
    "cost_amount": ["成本合价", "材料成本总价", "人工成本总价"],
    "cost_unit_price": ["成本单价", "成本价", "不含税单价"],
    "unit_price": [
        "综合单价（不含税）",
        "综合单价(不含税)",
        "综合单价",
        "不含税单价",
        "含税单价",
        "综合单价（不含税）",
    ],
    "amount": ["合价", "合计", "不含税合价", "含税合价"],
    "remark": ["备注", "说明"],
    "management": ["管理费"],
    "profit": ["利润"],
    "tax": ["税金", "税费"],
}

# 识别主表头：至少命中这些键
_PRIMARY_KEYS = ("name", "unit", "quantity")
# 或 name+unit（工程量可能在下一行子表头才出现）
_FALLBACK_KEYS = ("name", "unit")

SKIP_SHEET_KEYWORDS = (
    "封面",
    "报价说明",
    "报价汇总",
    "价格说明",
    "清单及价格",
    "汇总",
    "说明",
    "品牌",
    "材料表",
    "品牌表",
    "施工图纸",
    "图纸",
)


def _norm_header(text: Any) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    s = str(text).strip().replace("\r\n", "\n")
    s = re.sub(r"\s+", "", s.replace("\n", ""))
    return s


def _match_field(header: str, field: str) -> bool:
    h = _norm_header(header)
    if not h:
        return False
    if field == "quantity" and ("规则" in h or "计算规则" in h):
        return False
    for alias in FIELD_ALIASES.get(field, []):
        a = _norm_header(alias)
        if h == a:
            return True
        if len(a) >= 3 and a in h:
            if a == "单价" and ("成本" in h or "综合" in h):
                continue
            if a == "成本单价" and ("材料" in h or "人工" in h):
                continue
            if field == "quantity" and ("规则" in h or "适用范围" in h):
                continue
            if field == "feature" and "适用范围" in h:
                continue
            return True
    return False


def _score_header_row(row_values: List[Any]) -> Tuple[int, Dict[str, int]]:
    """返回 (得分, 列映射)。每字段取最佳匹配列（最长别名优先）。"""
    mapping: Dict[str, int] = {}
    hits = 0
    for field, aliases in FIELD_ALIASES.items():
        best_idx: Optional[int] = None
        best_score = 0
        for idx, val in enumerate(row_values):
            h = _norm_header(val)
            if not h:
                continue
            for alias in aliases:
                a = _norm_header(alias)
                if h == a:
                    score = 1000 + len(a)
                elif len(a) >= 3 and a in h:
                    if not _match_field(h, field):
                        continue
                    score = len(a)
                else:
                    continue
                if score > best_score:
                    best_score = score
                    best_idx = idx
        if best_idx is not None:
            mapping[field] = best_idx
            hits += 1
    primary = sum(1 for k in _PRIMARY_KEYS if k in mapping)
    fallback = sum(1 for k in _FALLBACK_KEYS if k in mapping)
    score = primary * 10 + fallback * 5 + hits
    return score, mapping


def _merge_subheader(
    main: Dict[str, int], sub: Dict[str, int], main_row: List[Any], sub_row: List[Any]
) -> Dict[str, int]:
    """合并双行表头；子行补充综合单价、成本列等。"""
    out = dict(main)
    fill_keys = (
        "unit_price",
        "amount",
        "remark",
        "cost_unit_price",
        "material_main",
        "material_loss_rate",
        "labor",
        "material_aux",
        "machinery",
        "management",
        "profit",
        "tax",
        "cost_amount",
        "spec",
    )
    for k in fill_keys:
        if k not in out and k in sub:
            out[k] = sub[k]

    # 同一表头行出现多个「合价」：靠后出现且位于成本单价之后 → 成本合价
    amount_idxs = [
        i
        for i, v in enumerate(sub_row)
        if _match_field(v, "amount") and not _match_field(v, "unit_price")
    ]
    if not amount_idxs:
        amount_idxs = [
            i
            for i, v in enumerate(main_row)
            if _match_field(v, "amount") and not _match_field(v, "unit_price")
        ]
    if len(amount_idxs) >= 2:
        cost_anchor = out.get("cost_unit_price", out.get("material_main", 999))
        for idx in amount_idxs:
            if idx > cost_anchor:
                out["cost_amount"] = idx
                break
        if "amount" not in out or out.get("amount") == out.get("cost_amount"):
            out["amount"] = amount_idxs[0]

    def _dup_indices(row_values: List[Any], field: str) -> List[int]:
        return [i for i, v in enumerate(row_values) if _match_field(v, field)]

    for row_values in (main_row, sub_row):
        mats = _dup_indices(row_values, "material_main")
        if len(mats) >= 2:
            out["material_main_cost"] = mats[1]
            out["_cost_side"] = 1
        for field, key in (
            ("labor", "labor_cost"),
            ("material_aux", "material_aux_cost"),
            ("machinery", "machinery_cost"),
            ("material_loss_rate", "material_loss_rate_cost"),
        ):
            idxs = _dup_indices(row_values, field)
            if len(idxs) >= 2:
                out[key] = idxs[1]
                out["_cost_side"] = 1
        cpus = _dup_indices(row_values, "cost_unit_price")
        if len(cpus) >= 2:
            out["cost_unit_price"] = cpus[1]
            out["_cost_side"] = 1

    return out


@dataclass
class SheetLayout:
    sheet_name: str
    header_row: int
    subheader_row: Optional[int]
    data_start_row: int
    column_map: Dict[str, int] = field(default_factory=dict)
    has_cost_block: bool = False


def detect_sheet_layout(df: pd.DataFrame, sheet_name: str) -> Optional[SheetLayout]:
    best_score = 0
    best_row = None
    best_map: Dict[str, int] = {}

    for i in range(min(35, len(df))):
        row = df.iloc[i].tolist()
        score, mapping = _score_header_row(row)
        if score > best_score and ("name" in mapping) and ("unit" in mapping):
            best_score = score
            best_row = i
            best_map = mapping

    if best_row is None:
        return None

    sub_row_idx = None
    merged = dict(best_map)
    main_row = df.iloc[best_row].tolist()
    merged = _merge_subheader(best_map, {}, main_row, main_row)

    if best_row + 1 < len(df):
        sub = df.iloc[best_row + 1].tolist()
        sub_score, sub_map = _score_header_row(sub)
        sub_joined = " ".join(_norm_header(v) for v in sub if _norm_header(v))
        is_subheader = (
            "综合单价" in sub_joined
            or "不含税单价" in sub_joined
            or "含税单价" in sub_joined
            or ("单价" in sub_joined and "合价" in sub_joined)
            or ("unit_price" in sub_map and "quantity" not in sub_map)
        )
        if is_subheader:
            sub_row_idx = best_row + 1
            merged = _merge_subheader(best_map, sub_map, main_row, sub)

    data_start = (sub_row_idx or best_row) + 1
    has_cost = any(
        k in merged
        for k in (
            "cost_unit_price",
            "unit_price",
            "material_main",
            "material_main_cost",
            "labor",
        )
    )

    return SheetLayout(
        sheet_name=sheet_name,
        header_row=best_row,
        subheader_row=sub_row_idx,
        data_start_row=data_start,
        column_map=merged,
        has_cost_block=has_cost,
    )


def _parse_qty(v: Any) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, str) and not v.strip():
        return None
    try:
        return float(str(v).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def is_pricing_row(row: Tuple[Any, ...], column_map: Dict[str, int]) -> bool:
    """有名称 + 单位 + (工程量 或 综合单价) → 需要报价。"""
    name_i = column_map.get("name")
    unit_i = column_map.get("unit")
    qty_i = column_map.get("quantity")
    if name_i is None or unit_i is None:
        return False
    name = _norm_header(row[name_i] if name_i < len(row) else "")
    unit = _norm_header(row[unit_i] if unit_i < len(row) else "")
    if not name or not unit:
        return False
    if "合计" in name.replace(" ", ""):
        return False
    if "小计" in name.replace(" ", ""):
        return False

    qty_ok = qty_i is not None and _parse_qty(row[qty_i] if qty_i < len(row) else None) is not None

    up_i = column_map.get("unit_price")
    if up_i is None:
        up_i = column_map.get("cost_unit_price")
    price_ok = False
    if up_i is not None and up_i < len(row):
        p = _parse_qty(row[up_i])
        price_ok = p is not None and p > 0

    return qty_ok or price_ok


def should_skip_sheet(sheet_name: str) -> bool:
    return any(k in sheet_name for k in SKIP_SHEET_KEYWORDS)
