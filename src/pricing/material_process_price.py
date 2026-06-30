# -*- coding: utf-8 -*-
"""项目主材编号价按清单特征工序分解（避免 PT-01=110 元/㎡ 盲目套整价）。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.normalize.feature_extract import extract_feature_profile
from src.normalize.text import normalize_name

# 主材表价为「饰面材料出厂价」的品类前缀
PAINT_CODE_PREFIXES = ("PT",)

# 含以下做法时，主材编号价不单独套价（应走龙骨/板材整项）
SUBSTRATE_BLOCK_KEYWORDS = (
    "轻钢龙骨",
    "石膏板",
    "玻镁板",
    "玻镁",
    "阻燃板",
    "木工板",
    "基层找平",
    "挂板",
)

# 完整肌理/无机涂料饰面 — 主材表价按饰面用量计入（「一底两面」属标准涂刷，非肌理）
TEXTURE_FINISH_KEYWORDS = (
    "肌理",
    "无机涂料饰面",
    "饰面层",
    "一底两面无机",
    "原顶涂料",
    "肌理漆",
    "肌理无机",
)

# 简易涂料项（地库 PT-01 一道等）— 主材仅为腻子/辅材，非 110 整价
LIGHT_COAT_KEYWORDS = (
    "涂料一道",
    "内墙涂料一道",
    "封闭底涂料一道",
    "涂料(包含",
)


@dataclass
class PaintProcessScope:
    putty_coats: int = 0
    has_primer: bool = False
    top_coats: int = 0
    texture_finish: bool = False
    light_coat_only: bool = False
    blocked_substrate: bool = False
    craft_points: List[str] = None

    def __post_init__(self):
        if self.craft_points is None:
            self.craft_points = []


def _count_putty_coats(text: str) -> int:
    m = re.search(r"刮(?:白胶)?腻子\s*([二两三34]|[0-9]+)\s*遍", text)
    if m:
        token = m.group(1)
        mapping = {"二": 2, "两": 2, "三": 3, "四": 4, "2": 2, "3": 3, "4": 4}
        return mapping.get(token, int(token) if token.isdigit() else 2)
    if "刮腻子" in text or "满批" in text:
        return 2
    if re.search(r"耐水腻子|腻子分遍|腻子找平|3厚.*腻子", text):
        return 2
    return 0


def _count_top_coats(text: str, prof_tags: dict, *, light_coat_only: bool) -> int:
    if light_coat_only or "涂料一道" in text:
        return 1 if ("涂料一道" in text or "封闭底涂料一道" in text) else 0
    if re.search(r"一底两面|一底二面", text):
        return 2
    if re.search(r"面漆\s*[二两三2-3]\s*遍|面漆2遍|两面", text):
        return 2
    if "面漆" in text or "涂料饰面" in text:
        return 1
    # paint_coats 标签可能来自「刮腻子两遍」，仅在有涂刷语境时采用
    if prof_tags.get("paint_coats") and re.search(r"面漆|底漆|乳胶漆|涂料饰面|一底两面", text):
        try:
            return int(prof_tags["paint_coats"])
        except ValueError:
            pass
    return 0


def analyze_paint_process(name: str, feature: str) -> PaintProcessScope:
    """从名称+特征解析涂料工序范围。"""
    text = normalize_name(f"{name}\n{feature}")
    prof = extract_feature_profile(feature, name)
    scope = PaintProcessScope(craft_points=prof.craft_points)

    if any(k in text for k in SUBSTRATE_BLOCK_KEYWORDS):
        scope.blocked_substrate = True
        return scope

    scope.putty_coats = _count_putty_coats(text)
    if re.search(r"一底两面|一底二面|一底2面", text) and "肌理" not in text:
        scope.has_primer = True
        scope.top_coats = 2
        scope.texture_finish = False
    else:
        scope.has_primer = bool(
            prof.tags.get("paint_primer")
            or re.search(r"底漆|封闭底|底涂", text)
        )
        scope.texture_finish = any(k in text for k in TEXTURE_FINISH_KEYWORDS) or (
            "无机涂料" in text and "饰面" in text
        )
    scope.light_coat_only = any(k in text for k in LIGHT_COAT_KEYWORDS) and not scope.texture_finish
    scope.top_coats = _count_top_coats(text, prof.tags, light_coat_only=scope.light_coat_only)
    return scope


# 无项目编号时饰面材料参考价（元/㎡，中档包工包料面漆材料价）
DEFAULT_FINISH_PRICE = {
    "low": {"latex": 32.0, "texture_inorganic": 95.0},
    "mid": {"latex": 38.0, "texture_inorganic": 110.0},
    "high": {"latex": 48.0, "texture_inorganic": 130.0},
}

PAINT_CRAFT_IDS = frozenset({"paint_wall", "paint_ceiling", "wall_gypsum_paint"})

PAINT_LINE_KEYWORDS = (
    "乳胶漆",
    "无机涂料",
    "涂料",
    "腻子",
    "面漆",
    "底漆",
    "肌理",
    "粉刷",
)


def is_paint_line_item(name: str, feature: str) -> bool:
    text = normalize_name(f"{name}\n{feature}")
    return any(k in text for k in PAINT_LINE_KEYWORDS)


def _apply_direct_cost_mode(comps: dict) -> dict:
    """简易/地库涂料金标准：直接费≈主材+人工，辅材机械不单列。"""
    mat = float(comps.get("material_main") or 0)
    if mat < 15.0:
        out = dict(comps)
        out["material_aux"] = 0.0
        out["machinery"] = 0.0
        return out
    return comps


def _decompose_from_scope(
    scope: PaintProcessScope,
    material_unit_price: float,
    *,
    material_code: str = "",
    material_name: str = "",
) -> Tuple[dict, str]:
    code_label = material_code or "乳胶漆饰面"
    note_parts = [f"腻子{scope.putty_coats}遍"]
    if scope.has_primer:
        note_parts.append("底漆")
    if scope.top_coats:
        note_parts.append(f"面漆{scope.top_coats}遍")
    if scope.texture_finish:
        note_parts.append("肌理/无机饰面")

    # --- 一底两面标准无机涂料（深海 PT-01≈31.9：主材≈腻子辅材）---
    if scope.has_primer and scope.top_coats >= 2 and not scope.texture_finish:
        mat = round(min(12.0, material_unit_price * 0.05), 2)
        labor = round(
            7.0 * max(scope.putty_coats, 1)
            + 4.0
            + 5.0 * scope.top_coats,
            2,
        )
        aux = round(1.2 * max(scope.putty_coats, 1) + 3.0, 2)
        note = f"[工序拆价·{code_label}]{'；'.join(note_parts)}；一底两面标准涂刷"
        return {
            "material_main": mat,
            "material_loss_rate": 0.0,
            "material_aux": aux,
            "labor": labor,
            "machinery": 0.2,
        }, note

    if scope.light_coat_only or (
        scope.putty_coats >= 1
        and not scope.texture_finish
        and scope.top_coats <= 1
        and "肌理" not in material_name
    ):
        mat = round(min(12.0, material_unit_price * 0.05), 2)
        labor = round(8.0 * max(scope.putty_coats, 2) + (3.0 if scope.has_primer else 2.0) + 2.0, 2)
        aux = round(0.5 * max(scope.putty_coats, 1), 2)
        note = (
            f"[工序拆价·{code_label}={material_unit_price:.0f}元/㎡·仅计辅材]"
            f"{'；'.join(note_parts)}；简易涂料项"
        )
        return _apply_direct_cost_mode({
            "material_main": mat,
            "material_loss_rate": 0.0,
            "material_aux": aux,
            "labor": labor,
            "machinery": 0.2,
        }), note

    if scope.texture_finish:
        finish_factor = 0.78
        mat = round(material_unit_price * finish_factor, 2)
        labor = round(
            9.0 * max(scope.putty_coats, 2)
            + (4.0 if scope.has_primer else 0.0)
            + 7.0 * max(scope.top_coats, 1)
            + 9.0,
            2,
        )
        aux = round(1.5 * max(scope.putty_coats, 1), 2)
        note = (
            f"[工序拆价·{code_label}={material_unit_price:.0f}元/㎡×{finish_factor:.0%}]"
            f"{'；'.join(note_parts)}"
        )
        return {
            "material_main": mat,
            "material_loss_rate": 0.0,
            "material_aux": aux,
            "labor": labor,
            "machinery": 0.3,
        }, note

    mat = round(material_unit_price * (0.08 + 0.1 * max(scope.top_coats, 1)), 2)
    labor = round(
        8.0 * max(scope.putty_coats, 1)
        + (3.5 if scope.has_primer else 0.0)
        + 6.0 * max(scope.top_coats, 1),
        2,
    )
    aux = round(1.2 * max(scope.putty_coats, 1), 2)
    note = f"[工序拆价·{code_label}]{'；'.join(note_parts)}；标准涂刷"
    return {
        "material_main": mat,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": labor,
        "machinery": 0.2,
    }, note


def lookup_paint_by_feature(
    name: str,
    feature: str,
    unit: str,
    *,
    craft_id: str = "",
    price_tier: str = "mid",
) -> Tuple[Optional[dict], str]:
    """无 PT 编号时按特征工序拆乳胶漆/无机涂料价。"""
    if craft_id and craft_id not in PAINT_CRAFT_IDS:
        return None, ""
    if not is_paint_line_item(name, feature):
        return None, ""

    scope = analyze_paint_process(name, feature)
    if scope.blocked_substrate:
        return None, f"[工序判断]含基层系统，不单套饰面工序价"

    tier_prices = DEFAULT_FINISH_PRICE.get(price_tier, DEFAULT_FINISH_PRICE["mid"])
    use_texture = scope.texture_finish
    finish_price = tier_prices["texture_inorganic"] if use_texture else tier_prices["latex"]
    comps, note = _decompose_from_scope(scope, finish_price)
    if scope.light_coat_only:
        return _apply_direct_cost_mode(comps), note
    return comps, note


def decompose_paint_material_price(
    material_code: str,
    material_name: str,
    material_unit_price: float,
    name: str,
    feature: str,
    unit: str,
) -> Tuple[Optional[dict], str]:
    """
    将项目主材表价（如 PT-01=110 元/㎡）按特征工序拆为人材机。
    返回 (components, note)；blocked 时返回 (None, note)。
    """
    prefix = material_code.split("-")[0].upper()
    if prefix not in PAINT_CODE_PREFIXES:
        return None, ""

    scope = analyze_paint_process(name, feature)
    if scope.blocked_substrate:
        return None, f"[工序判断]含基层系统({material_code})，不单套饰面主材价"

    if not scope.texture_finish and not scope.light_coat_only:
        if scope.has_primer and scope.top_coats >= 2:
            mat = round(min(12.0, material_unit_price * 0.05), 2)
            labor = 28.5 if re.search(r"天花|吊顶", name) else 19.5
            comps = {
                "material_main": mat,
                "material_loss_rate": 0.0,
                "material_aux": 6.0,
                "labor": labor,
                "machinery": 0.0,
            }
            if "投影面" in normalize_name(f"{name}\n{feature}"):
                comps = _apply_direct_cost_mode(comps)
            return comps, f"[工序拆价·{material_code}]一底两面标准涂刷（金标准口径）"
        material_unit_price = min(material_unit_price, DEFAULT_FINISH_PRICE["mid"]["latex"])

    comps, note = _decompose_from_scope(
        scope,
        material_unit_price,
        material_code=material_code,
        material_name=material_name,
    )
    if scope.light_coat_only:
        return _apply_direct_cost_mode(comps), note
    return comps, note
