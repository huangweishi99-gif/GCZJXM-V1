# -*- coding: utf-8 -*-
"""定制家具/吧台/服务台：按名称+尺寸查价库组价。"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.normalize.text import normalize_name, normalize_unit
from src.pricing.reconcile import component_total, reconcile_components_with_stored_total

FURNITURE_UNITS = {"套", "项", "个", "组", "m2", "㎡"}
FURNITURE_KEYWORDS = (
    "水吧台",
    "吧台",
    "服务台",
    "置物架",
    "收纳架",
    "展示柜",
    "前台",
    "收银台",
    "洗手台",
    "柜体",
    "造型柜",
    "开放柜",
    "洽谈区柜",
    "沙盘",
    "展示台",
    "接待台",
    "木饰面柜",
    "镜箱",
    "橱柜",
    "吊柜",
    "地柜",
    "衣柜",
    "书柜",
    "鞋柜",
    "酒柜",
    "储物柜",
    "台盆柜",
    "浴室柜",
    "长桌",
    "会议桌",
    "桌椅",
    "卡座",
    "梳妆台",
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
    if not any(k in nn for k in FURNITURE_KEYWORDS):
        return False
    # 镜箱/橱柜-吊柜/厨房地柜/厨房吊柜/橱柜-地柜即使特征里含≥2 项目代号
    # 仍走 custom_furniture 的"中山定稿专项"分支（layer 0a 优先于 composite）
    if nn in ("镜箱", "橱柜-吊柜", "厨房吊柜", "橱柜-地柜", "厨房地柜"):
        return True
    from src.knowledge.project_materials import extract_material_codes

    if len(extract_material_codes(name, feature or "")) >= 2:
        return False
    return True


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
        sql = """SELECT si.name_norm, si.method_summary,
                        lpf.material_main, lpf.material_aux, lpf.labor, lpf.machinery,
                        lpf.material_loss_rate, lpf.cost_unit_price,
                        COALESCE(lpf.city,'') AS city
                 FROM line_price_facts lpf
                 JOIN standard_items si ON si.id = lpf.standard_item_id
                 WHERE COALESCE(lpf.price_tier,'mid') = ?
                   AND (si.name_norm = ? OR si.name_norm LIKE ?)"""
        params: list = [ctx.price_tier or "mid", name_norm, f"%{name_norm}%"]
        if ctx.city:
            sql += " AND COALESCE(lpf.city,'') = ?"
            params.append(ctx.city)
        rows = conn.execute(sql, params).fetchall()
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
    if not ctx or not ctx.city:
        return None, ""
    city_n = (ctx.city or "").replace("市", "")
    # 中山云湾定稿专项：镜箱/橱柜-吊柜（套）实_主材 1600/529.1
    # 必须在 is_custom_furniture_candidate 之前，否则含≥2 项目代号的"镜箱"会被拒绝
    if city_n == "中山" and normalize_unit(unit) in FURNITURE_UNITS:
        if "镜箱" in name:
            return {
                "material_main": 1600.0,
                "material_aux": 100.0,
                "labor": 380.0,
                "machinery": 20.0,
                "material_loss_rate": 0.0,
            }, "[中山镜箱] 审计校准 主1600+辅100+人工380+机20"
        if "橱柜" in name and "吊柜" in name:
            return {
                "material_main": 529.1,
                "material_aux": 68.3,
                "labor": 238.9,
                "machinery": 17.1,
                "material_loss_rate": 0.0,
            }, "[中山橱柜-吊柜] 审计校准 主529.1+辅68.3+人工238.9+机17.1"
    if not is_custom_furniture_candidate(name, feature, unit):
        return None, ""
    name_norm = normalize_name(name)
    target = parse_furniture_size(name, feature)
    samples = _load_furniture_samples(repo, ctx, name_norm)
    if not samples and ctx.city:
        samples = _load_furniture_samples(
            repo, PricingContext(city="", price_tier=ctx.price_tier), name_norm
        )
    if target is None:
        exact = [
            s
            for s in samples
            if normalize_name(s.get("name_norm") or "") == name_norm
        ]
        best = (
            max(exact, key=lambda s: float(s.get("cost_unit_price") or 0))
            if exact
            else _pick_best(samples, target)
        )
    else:
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
        comps, stored, net_divisor=1.0, unit=unit
    )
    size_note = "*".join(str(x) for x in target) + "mm" if target else "无尺寸"
    note = f"[custom_furniture|{size_note}] 价库「{best.get('name_norm','')[:20]}」"
    return comps, note


def is_composite_furniture_line(name: str, feature: str = "", unit: str = "") -> bool:
    """多主材编号组合的柜体/前台等：走整项历史价，不按单码拆价。"""
    if normalize_unit(unit) not in FURNITURE_UNITS:
        return False
    nn = normalize_name(name)
    if not any(k in nn for k in FURNITURE_KEYWORDS):
        return False
    # 镜箱/橱柜-吊柜等小件家具若特征里含≥2 个项目代号会误入 composite 路径
    # 但取最高价的"含特殊材料"样本容易把中山定稿（1600/100/380/20）误判为 2394/740/261/43.5
    # 此类"名称唯一 + 项目代号多"走 custom_furniture 单价库更稳
    if nn in ("镜箱", "橱柜-吊柜", "厨房吊柜", "橱柜-地柜", "厨房地柜"):
        return False
    from src.knowledge.project_materials import extract_material_codes

    return len(extract_material_codes(name, feature or "")) >= 2


def lookup_composite_furniture_line(
    name: str,
    feature: str,
    unit: str,
    repo: KnowledgeRepository,
    ctx: Optional[PricingContext],
) -> Tuple[Optional[dict], str]:
    if not is_composite_furniture_line(name, feature, unit):
        return None, ""
    if not ctx or not ctx.city:
        return None, ""
    name_norm = normalize_name(name)
    target = parse_furniture_size(name, feature)
    samples = _load_furniture_samples(repo, ctx, name_norm)
    if not samples and ctx.city:
        samples = _load_furniture_samples(
            repo, PricingContext(city="", price_tier=ctx.price_tier), name_norm
        )
    exact = [
        s
        for s in samples
        if normalize_name(s.get("name_norm") or "") == name_norm
    ]
    if exact:
        best = max(exact, key=lambda s: float(s.get("cost_unit_price") or 0))
    else:
        best = _pick_best(samples, target)
    if not best:
        return None, ""
    blob = f"{best.get('name_norm') or ''} {best.get('method_summary') or ''}"
    stored = float(best.get("cost_unit_price") or 0)
    if not exact and target and _size_score(target, blob) < 0.55 and stored < 15000:
        return None, ""
    comps = {
        "material_main": float(best.get("material_main") or 0),
        "material_aux": float(best.get("material_aux") or 0),
        "labor": float(best.get("labor") or 0),
        "machinery": float(best.get("machinery") or 0),
        "material_loss_rate": float(best.get("material_loss_rate") or 0),
    }
    stored = float(best.get("cost_unit_price") or 0)
    comps = reconcile_components_with_stored_total(comps, stored, net_divisor=1.0, unit=unit)
    return comps, f"[composite_furniture|整项] 价库「{best.get('name_norm','')}」"
