"""清单去重：相同 名称+单位+做法 只保留一条母项。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.ingest.parser import ParsedLine, parse_workbook
from src.normalize.feature_extract import extract_feature_profile
from src.normalize.text import normalize_name, normalize_unit


@dataclass(frozen=True)
class MasterRowRef:
    """工作簿内母行定位（用于同表/跨表 lj 链接）。"""

    sheet: str
    row: int


def master_cell_formula(ref: MasterRowRef, col_letter: str, local_sheet: str) -> str:
    """生成 Excel 全绝对引用公式（铁律：母行链接必须绝对引用，行列均加 $）。

    与 lj 工具/历史清单引用方式一致（如 `=$U$7`、`='地上装修工程'!$Q$1`）：
    母行/费率单元格一律 `$列$行`，保证筛选、排序、移动单元格后引用目标不漂移。
    """
    if ref.sheet == local_sheet:
        return f"=${col_letter}${ref.row}"
    safe = ref.sheet.replace("'", "''")
    return f"='{safe}'!${col_letter}${ref.row}"


@dataclass
class DedupeItem:
    key: str
    name: str
    feature: str
    unit: str
    method_summary: str
    method_signature: str
    quantity_total: float
    line_count: int
    source_rows: List[Tuple[str, int, str]] = field(default_factory=list)
    cost_unit_price: Optional[float] = None
    material_main: Optional[float] = None
    labor: Optional[float] = None
    material_aux: Optional[float] = None
    machinery: Optional[float] = None


def make_dedupe_key(name: str, feature: str, unit: str) -> Tuple[str, str, str]:
    prof = extract_feature_profile(feature, name)
    return (
        normalize_name(name),
        normalize_unit(unit),
        prof.signature(),
    )


def dedupe_from_parsed_lines(lines: List[ParsedLine]) -> List[DedupeItem]:
    buckets: Dict[Tuple[str, str, str], DedupeItem] = {}

    for line in lines:
        if not line.name or not line.unit or line.quantity is None:
            continue
        nn, un, sig = make_dedupe_key(line.name, line.feature, line.unit)
        key_tuple = (nn, un, sig)
        prof = extract_feature_profile(line.feature, line.name)

        if key_tuple not in buckets:
            buckets[key_tuple] = DedupeItem(
                key=f"{nn}|{sig}|{un}",
                name=line.name,
                feature=line.feature or "",
                unit=line.unit,
                method_summary=prof.summary(),
                method_signature=sig,
                quantity_total=0.0,
                line_count=0,
                cost_unit_price=line.cost_unit_price,
                material_main=line.material_main,
                labor=line.labor,
                material_aux=line.material_aux,
                machinery=line.machinery,
            )
        item = buckets[key_tuple]
        item.quantity_total += float(line.quantity or 0)
        item.line_count += 1
        item.source_rows.append((line.sheet_name, line.row_index, line.seq))
        if line.cost_unit_price and not item.cost_unit_price:
            item.cost_unit_price = line.cost_unit_price
            item.material_main = line.material_main
            item.labor = line.labor
            item.material_aux = line.material_aux
            item.machinery = line.machinery

    return sorted(buckets.values(), key=lambda x: (-x.line_count, x.name))


def dedupe_workbook(path: str) -> List[DedupeItem]:
    return dedupe_from_parsed_lines(parse_workbook(path).lines)


def build_row_map(items: List[DedupeItem]) -> Dict[Tuple[str, int], int]:
    mapping: Dict[Tuple[str, int], int] = {}
    for i, item in enumerate(items):
        master_row = i + 2
        for sheet, row_idx, _ in item.source_rows:
            mapping[(sheet, row_idx)] = master_row
    return mapping
