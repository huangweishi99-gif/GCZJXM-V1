# -*- coding: utf-8 -*-
"""价库合价与人材机分量对齐（含成本区净价口径）。"""
from __future__ import annotations

from typing import Any, Mapping

from src.normalize.text import normalize_unit
from src.pricing.cost_basis import get_net_divisor, prefer_net_price

FURNITURE_UNITS = ("套", "项", "个", "组")


def component_total(comps: Mapping[str, Any]) -> float:
    mm = float(comps.get("material_main") or 0)
    loss = float(comps.get("material_loss_rate") or 0)
    return (
        mm * (1 + loss)
        + float(comps.get("material_aux") or 0)
        + float(comps.get("labor") or 0)
        + float(comps.get("machinery") or 0)
    )


def reconcile_components_with_stored_total(
    comps: dict,
    stored_total: float,
    *,
    threshold: float = 0.92,
    net_divisor: float = 1.0,
    unit: str = "",
    name: str = "",
    feature: str = "",
) -> dict:
    """价库 cost_unit_price 与分量对齐；套/项整价或分量偏少时按 net_divisor 折净价。"""
    if stored_total <= 0:
        return comps
    comp_total = component_total(comps)
    if comp_total <= 0:
        return comps

    u = normalize_unit(unit)
    target = stored_total
    ratio = comp_total / stored_total

    if net_divisor > 1.0:
        if ratio < 0.52:
            target = round(stored_total / net_divisor, 2)
        elif u in FURNITURE_UNITS and stored_total >= 3000:
            target = round(stored_total / net_divisor, 2)
        elif stored_total >= 35 and 0.55 <= ratio <= 0.98 and prefer_net_price(name, feature, unit):
            # 价库合价常含约 10% 管理费/利润，用户成本区为净价
            target = round(stored_total / net_divisor, 2)
    elif ratio < 0.52:
        target = round(stored_total / 1.1, 2)

    if target >= comp_total * threshold and abs(target - comp_total) < 0.02:
        return comps

    if target < comp_total and target > 0:
        scale = target / comp_total
        out = dict(comps)
        for key in ("material_main", "material_aux", "labor", "machinery"):
            out[key] = round(float(out.get(key) or 0) * scale, 2)
        drift = target - component_total(out)
        if abs(drift) >= 0.01:
            out["material_aux"] = float(out.get("material_aux") or 0) + drift
        return out

    if comp_total >= stored_total * threshold:
        return comps

    out = dict(comps)
    out["material_aux"] = float(out.get("material_aux") or 0) + (target - comp_total)
    return out
