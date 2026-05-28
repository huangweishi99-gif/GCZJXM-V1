"""从历史成本聚合「工艺类型×城市×档位」人材机价型库。"""
from __future__ import annotations

import json
import statistics
from typing import Any, Dict, List, Optional, Tuple

from src.knowledge.query import PricingContext
from src.normalize.feature_extract import extract_feature_profile
from src.normalize.text import normalize_unit
from src.normalize.craft_classifier import classify_craft


def _median(vals: List[float]) -> float:
    vals = [v for v in vals if v is not None and v > 0]
    if not vals:
        return 0.0
    return float(statistics.median(vals))


def _tag_suffix(tags: dict, tag_keys: List[str]) -> Tuple[str, str]:
    """取影响单价的关键标签作为子桶。"""
    for k in tag_keys:
        if k in tags:
            return k, str(tags[k])
    return "", ""


def rebuild_craft_cost_profiles(conn) -> int:
    """扫描 cost_records，按工艺类型聚合写入 craft_cost_profiles。"""
    rows = conn.execute(
        """SELECT cr.material_main, cr.material_loss_rate, cr.material_aux,
                  cr.labor, cr.machinery, cr.cost_unit_price,
                  si.name_norm, bl.feature, bl.unit, bl.name,
                  COALESCE(p.city, '') AS city,
                  COALESCE(p.price_tier, 'mid') AS price_tier
           FROM cost_records cr
           JOIN standard_items si ON si.id = cr.standard_item_id
           LEFT JOIN boq_lines bl ON bl.id = cr.source_line_id
           JOIN projects p ON p.id = cr.source_project_id
           WHERE cr.cost_unit_price > 0"""
    ).fetchall()

    buckets: Dict[tuple, list] = {}
    for r in rows:
        name = r["name"] or r["name_norm"] or ""
        feature = r["feature"] or ""
        unit = r["unit"] or "㎡"
        craft = classify_craft(name, feature, unit)
        prof = extract_feature_profile(feature, name)
        tk, tv = _tag_suffix(prof.tags, craft.tag_keys)
        key = (
            craft.craft_id,
            craft.trade,
            tk,
            tv,
            normalize_unit(unit),
            r["city"] or "",
            r["price_tier"] or "mid",
        )
        buckets.setdefault(key, []).append(dict(r))

    conn.execute("DELETE FROM craft_cost_profiles")
    updated = 0
    for key, recs in buckets.items():
        craft_id, trade, tk, tv, unit_n, city, tier = key
        if len(recs) < 1:
            continue
        main = _median([x["material_main"] for x in recs])
        aux = _median([x["material_aux"] for x in recs])
        labor = _median([x["labor"] for x in recs])
        mach = _median([x["machinery"] for x in recs])
        total = _median([x["cost_unit_price"] for x in recs])
        if total <= 0:
            total = main + aux + labor + mach
        main_s = main / total if total > 0 else 0
        aux_s = aux / total if total > 0 else 0
        labor_s = labor / total if total > 0 else 0
        mach_s = mach / total if total > 0 else 0
        conf = min(0.92, 0.45 + 0.04 * len(recs))

        conn.execute(
            """INSERT INTO craft_cost_profiles
               (craft_type, trade, tag_key, tag_value, unit_norm, city, price_tier,
                material_main, material_loss_rate, material_aux, labor, machinery,
                cost_unit_price, main_share, aux_share, labor_share, mach_share,
                sample_count, confidence_base, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now','localtime'))""",
            (
                craft_id,
                trade,
                tk,
                tv,
                unit_n,
                city,
                tier,
                main,
                _median([x["material_loss_rate"] for x in recs]),
                aux,
                labor,
                mach,
                total,
                main_s,
                aux_s,
                labor_s,
                mach_s,
                len(recs),
                conf,
            ),
        )
        updated += 1
    return updated


def lookup_craft_profile(
    conn,
    craft_id: str,
    unit: str,
    *,
    tag_key: str = "",
    tag_value: str = "",
    ctx: Optional[PricingContext] = None,
) -> Optional[dict]:
    """查工艺价型：优先同城同档+标签，再放宽。"""
    unit_n = normalize_unit(unit)
    city = ctx.city if ctx else ""
    tier = ctx.price_tier if ctx else "mid"

    def _q(c: str, t: str, tk: str, tv: str) -> Optional[dict]:
        row = conn.execute(
            """SELECT * FROM craft_cost_profiles
               WHERE craft_type=? AND unit_norm=? AND city=? AND price_tier=?
                 AND tag_key=? AND tag_value=?
               ORDER BY sample_count DESC LIMIT 1""",
            (craft_id, unit_n, c, t, tk, tv),
        ).fetchone()
        return dict(row) if row else None

    for c, t, tk, tv in [
        (city, tier, tag_key, tag_value),
        (city, tier, tag_key, ""),
        (city, tier, "", ""),
        ("", tier, tag_key, tag_value),
        ("", tier, "", ""),
    ]:
        row = _q(c, t, tk, tv)
        if row and row.get("sample_count", 0) >= 1:
            return row
    return None
