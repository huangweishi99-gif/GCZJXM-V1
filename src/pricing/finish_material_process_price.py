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
    """地面石材湿贴 / 墙面干挂铺工（海德/深海口径）。"""
    if re.search(r"干挂", text):
        return 145.0
    if re.search(r"70mm|20mm.*砂浆|DS-M15", text):
        return 140.0
    if re.search(r"墙面|墙身", text) or "墙面" in name:
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
    main = material_unit_price
    if re.search(r"玻镁板|镀锌方通|方通", text) and material_unit_price > 600:
        main = 450.0
        labor = 125.0 if re.search(r"湿贴", text) else 150.0
    elif re.search(r"20mm", text) and re.search(r"地面|楼地面", text + name):
        if re.search(r"拼花", text):
            main = round(material_unit_price * 1.66, 2)
        elif re.search(r"波打", text):
            pass
        elif material_code.upper().startswith("ST-03"):
            main = round(material_unit_price * 0.944, 2)
        elif material_code.upper().startswith("ST-06"):
            main = round(material_unit_price * 1.31, 2)
        else:
            main = round(material_unit_price * 1.22, 2)
    if re.search(r"不锈钢线条", text):
        main = round(main + 155.0, 2)
    elif re.search(r"波浪", text) and re.search(r"干挂", text):
        main = round(max(main, material_unit_price * 1.25), 2)
    if re.search(r"拼花|波打", text):
        labor = 130.0
    mach = round(max(12.0, material_unit_price * 0.022), 2)
    note = (
        f"[工序拆价·{material_code}={material_unit_price:.0f}元/㎡·石材]"
        f"湿贴；主材{main:.0f}，人工{labor:.0f}+辅材{aux}"
    )
    return {
        "material_main": main,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": labor,
        "machinery": mach,
    }, note


WOOD_VENEER_PREFIXES = ("WD",)


def decompose_wood_veneer_material_price(
    material_code: str,
    material_name: str,
    material_unit_price: float,
    name: str,
    feature: str,
    unit: str,
) -> Tuple[Optional[dict], str]:
    """木饰面墙面：表价 + 阻燃板/龙骨基层增量。"""
    prefix = material_code.split("-")[0].upper()
    if prefix not in WOOD_VENEER_PREFIXES:
        return None, ""

    text = normalize_name(f"{name}\n{feature}")
    if re.search(r"平开门|门扇|DR\d", name, re.I):
        return None, ""
    if not re.search(r"木饰面|WD", text) and "WD" not in material_code.upper():
        return None, ""

    labor = 75.0
    aux = 35.0
    mach = 15.0
    main = material_unit_price
    code_u = material_code.upper()
    has_substrate = bool(re.search(r"阻燃板|轻钢龙骨|钢结构", text)) or "墙面" in name
    if has_substrate:
        if code_u.startswith("WD-03"):
            main = round(material_unit_price * 2.2, 2)
            aux = 123.75 if material_unit_price >= 500 else round(material_unit_price * 0.21, 2)
        elif code_u.startswith("WD-04"):
            main = material_unit_price
            aux = 35.0
        else:
            main = round(material_unit_price * 2.2, 2)
            aux = 123.75 if material_unit_price >= 500 else round(material_unit_price * 0.21, 2)

    note = (
        f"[工序拆价·{material_code}={material_unit_price:.0f}元/㎡·木饰面]"
        f"主材{main:.0f}，人工{labor:.0f}+辅材{aux:.0f}"
    )
    return {
        "material_main": main,
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

    if code_u.startswith("GL-04"):
        main = material_unit_price
        aux = 12.0
        if re.search(r"平开门|移门|门", name):
            labor = 135.0
            main = round(material_unit_price * 3.54, 2)
    elif re.search(r"MT-01|不锈钢.*边框|不锈钢饰面", text):
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
