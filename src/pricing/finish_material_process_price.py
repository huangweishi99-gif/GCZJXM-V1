# -*- coding: utf-8 -*-
"""ST/WF/VF 等项目主材表价按特征工序分解（表价=饰面/板材采购价，非铺贴综合价）。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from src.normalize.text import normalize_name

STONE_PREFIXES = ("ST",)
WOOD_PREFIXES = ("WF",)
VINYL_PREFIXES = ("VF",)
WALLPAPER_PREFIXES = ("WP",)


def _stone_install_labor(text: str, name: str) -> float:
    """地面石材湿贴：主材表价外固定铺工（海德/深海口径）。"""
    if re.search(r"70mm|20mm.*砂浆|DS-M15", text):
        return 140.0
    if re.search(r"墙面|墙身|干挂", text) or "墙面" in name:
        return 95.0
    return 130.0


def decompose_stone_material_price(
    material_code: str,
    material_name: str,
    material_unit_price: float,
    name: str,
    feature: str,
    unit: str,
) -> Tuple[Optional[dict], str]:
    prefix = material_code.split("-")[0].upper()
    if prefix not in STONE_PREFIXES:
        return None, ""

    text = normalize_name(f"{name}\n{feature}\n{material_name}")
    if re.search(r"晶面|结晶|养护", text):
        return None, ""

    labor = _stone_install_labor(text, name)
    aux = 46.2
    if re.search(r"粘结剂|干混砂浆|云石胶|防护", text):
        aux = 46.2
    mach = round(max(12.0, material_unit_price * 0.022), 2)
    note = (
        f"[工序拆价·{material_code}={material_unit_price:.0f}元/㎡·石材]"
        f"湿贴；主材=表价，人工{labor:.0f}+辅材{aux}"
    )
    return {
        "material_main": material_unit_price,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": labor,
        "machinery": mach,
    }, note


def decompose_wood_floor_material_price(
    material_code: str,
    material_name: str,
    material_unit_price: float,
    name: str,
    feature: str,
    unit: str,
) -> Tuple[Optional[dict], str]:
    prefix = material_code.split("-")[0].upper()
    if prefix not in WOOD_PREFIXES:
        return None, ""

    text = normalize_name(f"{name}\n{feature}")
    if not re.search(r"木地板|地板|WF", text):
        return None, ""

    aux = 17.5
    if re.search(r"自流平", text):
        aux = 17.5
    if re.search(r"防潮膜", text):
        aux = max(aux, 17.5)

    note = (
        f"[工序拆价·{material_code}={material_unit_price:.0f}元/㎡·木地板]"
        f"主材=表价，铺工36+辅材{aux}"
    )
    return {
        "material_main": material_unit_price,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": 36.0,
        "machinery": 11.5,
    }, note


def decompose_wallpaper_material_price(
    material_code: str,
    material_name: str,
    material_unit_price: float,
    name: str,
    feature: str,
    unit: str,
) -> Tuple[Optional[dict], str]:
    prefix = material_code.split("-")[0].upper()
    if prefix not in WALLPAPER_PREFIXES:
        return None, ""

    text = normalize_name(f"{name}\n{feature}")
    if re.search(r"阻燃板|副龙骨|基层", text):
        labor, aux, mach = 76.5, 56.5, 60.2
    else:
        labor, aux, mach = 55.0, 35.0, 15.0

    note = (
        f"[工序拆价·{material_code}={material_unit_price:.0f}元/㎡·墙布]"
        f"主材=表价，铺工{labor}+辅材{aux}"
    )
    return {
        "material_main": material_unit_price,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": labor,
        "machinery": mach,
    }, note


def decompose_vinyl_floor_material_price(
    material_code: str,
    material_name: str,
    material_unit_price: float,
    name: str,
    feature: str,
    unit: str,
) -> Tuple[Optional[dict], str]:
    prefix = material_code.split("-")[0].upper()
    if prefix not in VINYL_PREFIXES:
        return None, ""

    if "水磨石" in material_name or re.search(r"VF-01", material_code, re.I):
        labor, aux = 80.0, 45.9
    else:
        labor, aux = 45.5, 18.0

    note = (
        f"[工序拆价·{material_code}={material_unit_price:.0f}元/㎡·地胶/卷材]"
        f"主材=表价，人工{labor}+辅材{aux}"
    )
    return {
        "material_main": material_unit_price,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": labor,
        "machinery": 12.0,
    }, note


GLASS_PREFIXES = ("GL",)


def decompose_glass_material_price(
    material_code: str,
    material_name: str,
    material_unit_price: float,
    name: str,
    feature: str,
    unit: str,
) -> Tuple[Optional[dict], str]:
    """玻璃隔断/饰面：主材表价 + 不锈钢框/深化费 + 安装工。"""
    prefix = material_code.split("-")[0].upper()
    if prefix not in GLASS_PREFIXES:
        return None, ""

    text = normalize_name(f"{name}\n{feature}\n{material_name}")
    if re.search(r"电动移门|移门电机|电机\(门机|定制成品.*门", text) or re.search(
        r"电动移门|DR\d+", name, re.I
    ):
        return None, "[工序判断]定制电动移门须整项历史价，不单套玻璃表价"

    labor = 110.0
    aux = 15.0
    mach = 12.0
    code_u = material_code.upper()

    if re.search(r"MT-01|不锈钢.*边框|不锈钢饰面", text):
        frame = 300.0 if code_u.startswith("GL-02") else 315.0
        main = round(material_unit_price + frame, 2)
        aux = 65.0 if code_u.startswith("GL-01") else 15.0
    elif re.search(r"隔断|固定玻璃", name):
        main = round(material_unit_price + 315.0, 2)
        aux = 65.0
    else:
        main = round(material_unit_price + 90.0, 2)

    note = (
        f"[工序拆价·{material_code}={material_unit_price:.0f}元/㎡·玻璃]"
        f"主材含框/玻璃{main:.0f}，人工{labor:.0f}+辅材{aux}"
    )
    return {
        "material_main": main,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": labor,
        "machinery": mach,
    }, note
