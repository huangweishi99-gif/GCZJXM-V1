# -*- coding: utf-8 -*-
"""定制家具/吧台/服务台：按名称+尺寸查价库组价。"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.normalize.text import normalize_name, normalize_unit
from src.pricing.reconcile import component_total, reconcile_components_with_stored_total

FURNITURE_UNITS = {"套", "项", "个", "组"}
FURNITURE_KEYWORDS = (
    "水吧台",
    "吧台",
    "服务台",
    "置物架",
    "展示柜",
    "前台",
    "收银台",
    "洗手台",
    "柜体",
    "造型柜",
)
SIZE3_RE = re.compile(
    r"(\d{3,5})\s*mm?\s*[*×xX]\s*(\d{2,5})\s*mm?\s*[*×xX]\s*(\d{2,5})",
    re.I,
)
SIZE2_RE = re.compile(r"(\d{3,5})\s*mm?\s*[*×xX]\s*(\d{2,5})", re.I)


def parse_furniture_size(name: str, feature: str = "") -> Optional[Tuple[int, ...]]:
    text = f"{name} {feature}"
    m3 = SIZE3_RE.search(text)
    if m3:
        return int(m3.group(1)), int(m3.group(2)), int(m3.group(3))
    m2 = SIZE2_RE.search(text)
    if m2:
        return int(m2.group(1)), int(m2.group(2))
    return None


def is_custom_furniture_candidate(name: str, feature: str = "", unit: str = "") -> bool:
    if normalize_unit(unit) not in FURNITURE_UNITS:
        return False
    nn = normalize_name(name)
    return any(k in nn for k in FURNITURE_KEYWORDS)


def _size_metric(dims: Optional[Tuple[int, ...]]) -> float:
    if not dims:
        return 0.0
    m = 1.0
    for d in dims:
        m *= float(d)
    return m


def _size_score(target: Optional[Tuple[int, ...]], blob: str) -> float:
    if not target:
        return 0.45
    cand = parse_furniture_size(blob, blob)
    if not cand:
        return 0.2
    t = _size_metric(target)
    c = _size_metric(cand)
    if t <= 0 or c <= 0:
        return 0.2
    if target == cand:
        return 1.0
    ratio = min(t, c) / max(t, c)
    return 0.35 + 0.65 * ratio


def _load_furniture_samples(
    repo: KnowledgeRepository, ctx: PricingContext, name_norm: str
) -> List[dict]:
    conn = repo.conn()
    try:
        rows = conn.execute(
            """SELECT si.name_norm, si.method_summary,
                      lpf.material_main, lpf.material_aux, lpf.labor, lpf.machinery,
                      lpf.material_loss_rate, lpf.cost_unit_price
               FROM line_price_facts lpf
               JOIN standard_items si ON si.id = lpf.standard_item_id
               WHERE COALESCE(lpf.city,'') = ? AND COALESCE(lpf.price_tier,'mid') = ?
                 AND si.name_norm = ?""",
            (ctx.city or "", ctx.price_tier or "mid", name_norm),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _pick_best(samples: List[dict], target_size: Optional[Tuple[int, ...]]) -> Optional[dict]:
    if not samples:
        return None
    scored: List[Tuple[float, dict]] = []
    for s in samples:
        blob = f"{s.get('name_norm') or ''} {s.get('method_summary') or ''}"
        price = float(s.get("cost_unit_price") or 0)
        if price <= 0:
            continue
        scored.append((_size_score(target_size, blob), s))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def lookup_custom_furniture_price(
    name: str,
    feature: str,
    unit: str,
    repo: KnowledgeRepository,
    ctx: Optional[PricingContext],
    *,
    net_divisor: float = 1.0,
) -> Tuple[Optional[dict], str]:
    if not is_custom_furniture_candidate(name, feature, unit):
        return None, ""
    if not ctx or not ctx.city:
        return None, ""
    name_norm = normalize_name(name)
    target = parse_furniture_size(name, feature)
    samples = _load_furniture_samples(repo, ctx, name_norm)
    best = _pick_best(samples, target)
    if not best:
        return None, ""
    comps = {
        "material_main": float(best.get("material_main") or 0),
        "material_aux": float(best.get("material_aux") or 0),
        "labor": float(best.get("labor") or 0),
        "machinery": float(best.get("machinery") or 0),
        "material_loss_rate": float(best.get("material_loss_rate") or 0),
    }
    stored = float(best.get("cost_unit_price") or 0)
    comps = reconcile_components_with_stored_total(
        comps, stored, net_divisor=net_divisor, unit=unit
    )
    size_note = "*".join(str(x) for x in target) + "mm" if target else "无尺寸"
    note = f"[custom_furniture|{size_note}] 价库「{best.get('name_norm','')[:20]}」"
    return comps, note
