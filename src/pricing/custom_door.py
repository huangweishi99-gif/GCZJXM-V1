# -*- coding: utf-8 -*-
"""定制门/门套：按名称规格尺寸查价库组价。"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.normalize.text import normalize_unit, normalize_name

SIZE_RE = re.compile(r"(\d{3,4})\s*[*×xX]\s*(\d{3,4})")
DOOR_UNITS = {"樘", "套", "扇", "项"}
DOOR_M2_UNITS = {"m2", "㎡", "平方"}

DOOR_RULES = (
    ("fire_door", ("防火门", "甲级防火", "乙级防火", "丙级防火")),
    ("stone_frame", ("石材门套", "石饰面门", "电梯门", "电梯厅门", "电梯石")),
    ("wood_door", ("木饰面门", "木门", "入户门")),
    ("door_frame", ("门套",)),
)


def parse_door_size(name: str, feature: str = "") -> Optional[Tuple[int, int]]:
    m = SIZE_RE.search(f"{name} {feature}")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def classify_door_type(name: str, feature: str = "") -> str:
    text = f"{name} {feature}"
    if re.search(r"石.{0,3}门|石饰面门|石材门", text):
        return "stone_frame"
    for dtype, keys in DOOR_RULES:
        if dtype == "stone_frame":
            continue
        if any(k in text for k in keys):
            return dtype
    if "门" in text and parse_door_size(name, feature):
        return "door_generic"
    return ""


def is_door_whole_line(name: str, feature: str = "") -> bool:
    """定制门/门套整项组价（㎡ 或 樘），不单套饰面主材编号表。"""
    if not re.search(r"门", name):
        return False
    text = normalize_name(f"{name}\n{feature}")
    if re.search(r"DR\d", name, re.I):
        return True
    if re.search(r"定制成品|门扇|套装门", text):
        return True
    if re.search(r"清洁间门|平开门|转轴门|防火门|推拉门|隐形门", name):
        return True
    if "门套" in name:
        return True
    return False


def is_custom_door_candidate(name: str, feature: str = "", unit: str = "") -> bool:
    if normalize_unit(unit) not in DOOR_UNITS:
        return False
    return bool(classify_door_type(name, feature))


def _size_score(target: Optional[Tuple[int, int]], name_norm: str) -> float:
    if not target:
        return 0.5
    w, h = target
    cand = parse_door_size(name_norm, "")
    if not cand:
        return 0.2
    cw, ch = cand
    area_t = w * h
    area_c = cw * ch
    if area_c <= 0:
        return 0.2
    ratio = min(area_t, area_c) / max(area_t, area_c)
    if cw == w and ch == h:
        return 1.0
    return 0.4 + 0.6 * ratio


def _load_door_samples(repo: KnowledgeRepository, ctx: PricingContext) -> List[dict]:
    conn = repo.conn()
    try:
        rows = conn.execute(
            """SELECT si.name_norm, si.method_summary,
                      lpf.material_main, lpf.material_aux, lpf.labor, lpf.machinery,
                      lpf.material_loss_rate, lpf.cost_unit_price
               FROM line_price_facts lpf
               JOIN standard_items si ON si.id = lpf.standard_item_id
               WHERE COALESCE(lpf.city,'') = ? AND COALESCE(lpf.price_tier,'mid') = ?
                 AND si.unit_norm IN ('樘', '套', '扇', '项')
                 AND (si.name_norm LIKE '%门%' OR si.name_norm LIKE '%门套%')""",
            (ctx.city or "", ctx.price_tier or "mid"),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _pick_best(
    samples: List[dict],
    door_type: str,
    target_size: Optional[Tuple[int, int]],
    name: str,
) -> Optional[dict]:
    if not samples:
        return None
    keys = dict(DOOR_RULES).get(door_type, ())
    text = name
    scored: List[Tuple[float, dict]] = []
    for s in samples:
        nn = s.get("name_norm") or ""
        ms = s.get("method_summary") or ""
        blob = f"{nn} {ms}"
        if door_type == "fire_door":
            if "防火" not in blob or "门套" in nn:
                continue
            if re.search(r"石.{0,3}门", nn):
                continue
            type_hit = 1.0
        elif door_type == "stone_frame":
            if not re.search(r"(石.{0,3}门|门套|石饰面|电梯)", blob):
                continue
            if re.search(r"防火[^石]*门", nn) and not re.search(r"石.{0,3}门", nn):
                continue
            type_hit = 1.0
        else:
            type_hit = 1.0 if any(k in blob for k in keys) else (0.3 if door_type == "door_generic" else 0.0)
            if type_hit <= 0:
                continue
        if door_type == "fire_door" and "石材" in nn and "石材" not in text:
            continue
        size_s = _size_score(target_size, nn)
        price = float(s.get("cost_unit_price") or 0)
        if price <= 0:
            continue
        scored.append((type_hit * 0.55 + size_s * 0.45, s))
    if not scored:
        for s in samples:
            price = float(s.get("cost_unit_price") or 0)
            if price > 200:
                scored.append((_size_score(target_size, s.get("name_norm") or ""), s))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def lookup_custom_door_price(
    name: str,
    feature: str,
    unit: str,
    repo: KnowledgeRepository,
    ctx: Optional[PricingContext],
) -> Tuple[Optional[dict], str]:
    if not is_custom_door_candidate(name, feature, unit):
        return None, ""
    door_type = classify_door_type(name, feature)
    target = parse_door_size(name, feature)
    samples: List[dict] = []
    if ctx and ctx.city:
        samples = _load_door_samples(repo, ctx)
    best = _pick_best(samples, door_type, target, name)
    if not best:
        return None, ""
    comps = {
        "material_main": float(best.get("material_main") or 0),
        "material_aux": float(best.get("material_aux") or 0),
        "labor": float(best.get("labor") or 0),
        "machinery": float(best.get("machinery") or 0),
        "material_loss_rate": float(best.get("material_loss_rate") or 0),
    }
    stored_total = float(best.get("cost_unit_price") or 0)
    comp_total = (
        comps["material_main"] * (1 + comps["material_loss_rate"])
        + comps["material_aux"]
        + comps["labor"]
        + comps["machinery"]
    )
    target_total = stored_total
    if stored_total > 0 and comp_total > 0:
        ratio = comp_total / stored_total
        if ratio < 0.72:
            target_total = round(stored_total / 1.1, 2)
    if target_total > 0 and comp_total < target_total * 0.85:
        if door_type == "fire_door":
            comps = {
                "material_main": 0.0,
                "material_aux": round(target_total * 0.68, 2),
                "labor": round(target_total * 0.30, 2),
                "machinery": round(target_total * 0.02, 2),
                "material_loss_rate": 0.0,
            }
        else:
            comps = {
                "material_main": round(target_total * 0.58, 2),
                "material_aux": round(target_total * 0.08, 2),
                "labor": round(target_total * 0.32, 2),
                "machinery": round(target_total * 0.02, 2),
                "material_loss_rate": 0.0,
            }
    elif comp_total > 0 and target_total > comp_total * 1.02:
        comps["material_aux"] = float(comps.get("material_aux") or 0) + (target_total - comp_total)
    elif not any(comps[k] for k in ("material_main", "labor", "material_aux")):
        if stored_total <= 0:
            return None, ""
        tt = target_total if target_total > 0 else stored_total
        comps = {
            "material_main": round(tt * 0.65, 2),
            "material_aux": round(tt * 0.08, 2),
            "labor": round(tt * 0.25, 2),
            "machinery": round(tt * 0.02, 2),
            "material_loss_rate": 0.0,
        }
    size_note = f"{target[0]}*{target[1]}mm" if target else "无尺寸"
    note = f"[{door_type}|{size_note}] 价库「{best.get('name_norm','')[:24]}」"
    return comps, note


def lookup_door_whole_line_price(
    name: str,
    feature: str,
    unit: str,
    engine,
    repo: KnowledgeRepository,
    ctx: Optional[PricingContext],
) -> Tuple[Optional[dict], str]:
    """㎡ 定制门：放宽整项历史匹配（DR/套装门等）。"""
    if not is_door_whole_line(name, feature):
        return None, ""
    if normalize_unit(unit) not in DOOR_M2_UNITS:
        return None, ""

    from src.pricing.reference_resolve import line_reference_ok_door

    cands = engine.search(name, feature or "", unit, top_n=8)
    scope = f"（{ctx.scope_note()}）" if ctx else ""
    for c in cands:
        ok, _ = line_reference_ok_door(c, query_unit=unit)
        if not ok:
            continue
        sid = c["standard_item_id"]
        if ctx:
            fact, fnote = repo.get_line_fact(sid, ctx)
            if fact:
                total = float(fact.get("cost_unit_price") or 0)
                if total < 400:
                    continue
                note = (
                    f"[定制门整项]{fnote}{scope}「{c['name']}」"
                    f" 名称{c['name_score']:.0%} 特征{c['feature_score']:.0%}"
                )
                return {
                    "material_main": float(fact.get("material_main") or 0),
                    "material_loss_rate": float(fact.get("material_loss_rate") or 0),
                    "labor": float(fact.get("labor") or 0),
                    "material_aux": float(fact.get("material_aux") or 0),
                    "machinery": float(fact.get("machinery") or 0),
                }, note
        records = repo.get_cost_records_for_item(sid, ctx=ctx)
        if not records:
            continue
        agg = repo.aggregate_costs(records)
        total = float(agg.get("cost_unit_price") or agg.get("_cost_unit_price") or 0)
        if total < 400:
            continue
        note = (
            f"[定制门整项]「{c['name']}」"
            f" 名称{c['name_score']:.0%} 特征{c['feature_score']:.0%}；{len(records)}条样本{scope}"
        )
        return {
            "material_main": float(agg.get("material_main") or 0),
            "material_loss_rate": float(agg.get("material_loss_rate") or 0),
            "labor": float(agg.get("labor") or 0),
            "material_aux": float(agg.get("material_aux") or 0),
            "machinery": float(agg.get("machinery") or 0),
        }, note
    return None, ""
