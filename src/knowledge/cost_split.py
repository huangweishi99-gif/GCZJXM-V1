# -*- coding: utf-8 -*-
"""整价按工艺份额拆分为分项人材机（learn / judge 共用）。"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from src.normalize.craft_classifier import CraftMatch, classify_craft


def _component_total(comps: Mapping[str, Any]) -> float:
    mm = float(comps.get("material_main") or 0)
    loss = float(comps.get("material_loss_rate") or 0)
    return (
        mm * (1 + loss)
        + float(comps.get("material_aux") or 0)
        + float(comps.get("labor") or 0)
        + float(comps.get("machinery") or 0)
    )


def share_map(template: dict) -> dict:
    return {
        "material_main": template.get("main", template.get("material_main", 0.4)),
        "material_aux": template.get("aux", template.get("material_aux", 0.2)),
        "labor": template.get("labor", 0.36),
        "machinery": template.get("machinery", template.get("machinery", 0.02)),
    }


def components_usable(comps: Mapping[str, Any]) -> bool:
    return any(
        float(comps.get(k) or 0) > 0
        for k in ("material_main", "labor", "material_aux", "machinery")
    )


def component_sum(comps: Mapping[str, Any]) -> float:
    return sum(
        float(comps.get(k) or 0)
        for k in ("material_main", "material_aux", "labor", "machinery")
    )


def allocate_by_craft_template(total: float, craft: CraftMatch) -> dict:
    shares = share_map(craft.template_share)
    out = {
        key: round(total * shares[key], 2)
        for key in ("material_main", "material_aux", "labor", "machinery")
    }
    out["material_loss_rate"] = 0.0
    drift = round(total - _component_total(out), 2)
    if abs(drift) >= 0.01:
        out["labor"] = float(out.get("labor") or 0) + drift
    return out


def needs_component_split(
    cost_unit_price: float,
    material_main: float = 0,
    material_aux: float = 0,
    labor: float = 0,
    machinery: float = 0,
    *,
    ratio_threshold: float = 0.15,
) -> bool:
    if cost_unit_price <= 0:
        return False
    comp = material_main + material_aux + labor + machinery
    if comp <= 0.01:
        return True
    return comp / cost_unit_price < ratio_threshold


def split_whole_price_components(
    name: str,
    feature: str,
    unit: str,
    cost_unit_price: float,
    *,
    craft: Optional[CraftMatch] = None,
) -> dict:
    """按工艺份额模板将整价拆为主材/辅材/人工/机械。"""
    craft = craft or classify_craft(name, feature, unit)
    return allocate_by_craft_template(float(cost_unit_price), craft)
