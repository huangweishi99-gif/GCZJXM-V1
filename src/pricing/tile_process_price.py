# -*- coding: utf-8 -*-
"""CT 瓷砖编号价按特征工序分解（表价=砖材采购价，非铺贴综合价）。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from src.normalize.text import normalize_name, normalize_unit

TILE_CODE_PREFIXES = ("CT",)

# 踢脚：表价为整砖 元/㎡；清单按 ㎡(展开) 或 m(延米) 计量，人工/辅材随单位折算
_KICK_LABOR_M2 = 120.0
_KICK_AUX_M2 = 16.5
_KICK_MACH_M2 = 5.75
# 50mm 窄条踢脚：主材相对表价系数（海德金标准 105/55）
_KICK_MAT_FACTOR_50MM = 105.0 / 55.0
# 延米 ↔ 展开㎡(50mm) 折算系数（框架清单 12.84/(120×0.05)）
_M_PER_M2_AT_50MM = 12.84 / (_KICK_LABOR_M2 * 0.05)
# 延米主材：7.84/(55×0.05)
_MAT_M_PER_M2_TABLE_AT_50MM = 7.84 / (55.0 * 0.05)


def _parse_kick_height_mm(text: str) -> float:
    m = re.search(r"(\d+)\s*mm", text, re.I)
    if m:
        return max(10.0, float(m.group(1)))
    return 50.0


def _is_area_unit(unit: str) -> bool:
    return normalize_unit(unit) in ("m2", "㎡")


def _is_linear_unit(unit: str) -> bool:
    return normalize_unit(unit) in ("m", "米")


def decompose_ct_tile_kick(
    material_code: str,
    material_unit_price: float,
    name: str,
    feature: str,
    unit: str,
) -> Tuple[Optional[dict], str]:
    """CT 瓷砖踢脚：主材表价 + 按清单单位(㎡/m)拆铺工与辅材。"""
    if not material_code.upper().startswith("CT"):
        return None, ""

    text = normalize_name(f"{name}\n{feature}")
    if not re.search(r"踢脚", text):
        return None, ""

    height_mm = _parse_kick_height_mm(text)
    height_m = height_mm / 1000.0
    height_scale = 50.0 / height_mm
    line_unit = normalize_unit(unit)

    if _is_area_unit(line_unit):
        mat_factor = _KICK_MAT_FACTOR_50MM * height_scale
        material_main = round(material_unit_price * mat_factor, 2)
        labor = _KICK_LABOR_M2
        aux = _KICK_AUX_M2
        mach = _KICK_MACH_M2
        unit_note = f"清单㎡(展开)，高{height_mm:.0f}mm"
    elif _is_linear_unit(line_unit):
        material_main = round(
            material_unit_price * height_m * _MAT_M_PER_M2_TABLE_AT_50MM * height_scale,
            2,
        )
        labor = round(_KICK_LABOR_M2 * height_m * _M_PER_M2_AT_50MM * height_scale, 2)
        aux = round(_KICK_AUX_M2 * height_m * _M_PER_M2_AT_50MM * height_scale, 2)
        mach = round(_KICK_MACH_M2 * height_m * _M_PER_M2_AT_50MM * height_scale, 2)
        unit_note = f"清单延米，高{height_mm:.0f}mm折算"
    else:
        return None, ""

    note = (
        f"[工序拆价·{material_code}={material_unit_price:.0f}元/㎡·砖材]"
        f"瓷砖踢脚；{unit_note}；人工{labor}+辅材{aux}"
    )
    return {
        "material_main": material_main,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": labor,
        "machinery": mach,
    }, note


def decompose_tile_material_price(
    material_code: str,
    material_name: str,
    material_unit_price: float,
    name: str,
    feature: str,
    unit: str,
) -> Tuple[Optional[dict], str]:
    prefix = material_code.split("-")[0].upper()
    if prefix not in TILE_CODE_PREFIXES:
        return None, ""

    text = normalize_name(f"{name}\n{feature}")
    adhesive = bool(re.search(r"瓷砖胶|胶粘贴|胶粘剂|胶粘剂|背覆胶", text))
    mortar = bool(re.search(r"水泥砂浆|砂浆粘贴|干混砂浆", text))
    wall = bool(re.search(r"墙面|墙砖|墙身", text) or "墙面" in name)
    floor = bool(re.search(r"楼地面|地砖|地面", text) or "地面" in name)

    if re.search(r"踢脚", text):
        return decompose_ct_tile_kick(
            material_code, material_unit_price, name, feature, unit
        )

    # 项目主材表价 = 砖材 元/㎡，主材取表价（不用比例折算）
    mat_main = material_unit_price

    if wall and re.search(r"轻钢龙骨|水泥纤维板|阻燃板基层|焊网|钢丝网", text):
        labor = 89.0 if re.search(r"轻钢龙骨|水泥纤维板", text) else 71.0
        aux = 55.5 if re.search(r"轻钢龙骨|水泥纤维板", text) else 37.0
        note = (
            f"[工序拆价·{material_code}={material_unit_price:.0f}元/㎡·砖材]"
            f"墙面瓷砖+基层；主材=表价"
        )
        return {
            "material_main": mat_main,
            "material_loss_rate": 0.0,
            "material_aux": aux,
            "labor": labor,
            "machinery": 0.5,
        }, note

    if wall and adhesive:
        if re.search(r"钢丝网|焊网|钢筋", text):
            note = (
                f"[工序拆价·{material_code}={material_unit_price:.0f}元/㎡·砖材]"
                f"墙面瓷砖+焊网；主材=表价"
            )
            return {
                "material_main": mat_main,
                "material_loss_rate": 0.0,
                "material_aux": 37.0,
                "labor": 71.0,
                "machinery": 0.5,
            }, note
        note = (
            f"[工序拆价·{material_code}={material_unit_price:.0f}元/㎡·砖材]"
            f"墙面瓷砖胶；主材=表价"
        )
        return {
            "material_main": mat_main,
            "material_loss_rate": 0.0,
            "material_aux": 16.5,
            "labor": 45.0,
            "machinery": 0.5,
        }, note

    if floor and (mortar or not adhesive):
        labor = 90.0 if re.search(r"80mm|DS-M15|花砖", text) else 48.0
        if re.search(r"拼花", text):
            labor = 80.0
        note = f"[工序拆价·{material_code}]砂浆地砖；主材=表价"
        return {
            "material_main": mat_main,
            "material_loss_rate": 0.0,
            "material_aux": 14.0,
            "labor": labor,
            "machinery": 2.0,
        }, note

    if adhesive:
        note = f"[工序拆价·{material_code}]瓷砖胶铺贴；主材=表价"
        return {
            "material_main": mat_main,
            "material_loss_rate": 0.0,
            "material_aux": 14.0,
            "labor": 50.0,
            "machinery": 1.0,
        }, note

    return None, ""
