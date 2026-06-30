"""组价参考解析：名称+特征相似才整项参照；否则按材料规格查主材价。"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.match.engine import MatchThresholds
from src.normalize.text import normalize_unit
from src.pricing.engine import PricingEngine
from src.pricing.line_identity import check_pricing_identity, units_must_match
from src.pricing.material_lookup import MaterialPriceLookup


def _line_reference_ok(
    c: dict,
    th: MatchThresholds,
    cfg: dict,
    *,
    query_unit: str = "",
) -> Tuple[bool, str]:
    """整项参照须名称、特征、单位均有相似度/一致，不能只看综合分。"""
    ref = cfg.get("reference_line", {})
    name_min = ref.get("name_min", 0.55)
    feature_min = ref.get("feature_min", 0.42)
    total_min = ref.get("total_min", 0.58)
    tag_min = ref.get("tag_min", 0.45)

    if query_unit and c.get("unit"):
        if not units_must_match(query_unit, c["unit"]):
            return False, f"单位不一致({normalize_unit(query_unit)} vs {normalize_unit(c['unit'])})"

    has_feature = bool((c.get("feature") or "").strip())

    if c.get("conflicts"):
        return False, "做法标签冲突"

    strong_ok, _ = _line_reference_ok_strong_name(c, query_unit=query_unit)
    if strong_ok:
        return True, "同名称强匹配"

    if c["name_score"] < name_min:
        return False, f"名称相似度{c['name_score']:.0%}不足（需≥{name_min:.0%}）"

    if has_feature:
        if c["feature_score"] < feature_min:
            return False, f"特征相似度{c['feature_score']:.0%}不足（需≥{feature_min:.0%}）"
    elif c["name_score"] < 0.72:
        return False, "无特征描述且名称相似不足"

    if c["tag_score"] < tag_min:
        return False, f"做法一致度{c['tag_score']:.0%}不足"

    if c["total_score"] < total_min:
        return False, f"综合{c['total_score']:.0%}不足"

    return True, ""


def _line_reference_ok_strong_name(
    c: dict,
    *,
    query_unit: str = "",
) -> Tuple[bool, str]:
    """项目名称几乎一致 + 特征较像 + 单位一致 → 可整项参照（定制门/玻璃等标签差异大）。"""
    if c.get("name_score", 0) < 0.98:
        return False, ""
    if c.get("feature_score", 0) < 0.65:
        return False, ""
    if query_unit and c.get("unit"):
        if not units_must_match(query_unit, c["unit"]):
            return False, ""
    if c.get("conflicts"):
        return False, ""
    return True, "同名称强匹配"


def resolve_reference_costs(
    name: str,
    feature: str,
    unit: str,
    engine: PricingEngine,
    repo: KnowledgeRepository,
    *,
    reference_fill: bool = True,
    existing_components: Optional[dict] = None,
    existing_note: str = "",
    ctx: Optional[PricingContext] = None,
    exclude_standard_item_ids: Optional[set] = None,
) -> Tuple[Optional[dict], str]:
    """
    解析可填入的人材机分量与说明。
    1. 已有组价结果 → 直接用
    2. 名称+特征均相似的历史项 → 整项参照
    3. 否则 → 材料规格主材价（如 600*600 地砖）
    """
    if existing_components and any(existing_components.get(k) for k in (
        "material_main", "labor", "material_aux", "machinery"
    )):
        return existing_components, existing_note or ""

    if not reference_fill:
        return None, existing_note or "未匹配"

    id_cfg = repo.settings.get("line_identity", {})
    ok_id, id_reason = check_pricing_identity(
        name,
        feature,
        unit,
        require_unit=id_cfg.get("require_unit", True),
    )
    if not ok_id:
        return None, id_reason

    cfg = repo.settings.get("pricing", {})
    th = engine.thresholds
    scope = f"（{ctx.scope_note()}）" if ctx else ""

    cands = engine.search(
        name,
        feature or "",
        unit,
        top_n=3,
        exclude_standard_item_ids=exclude_standard_item_ids,
    )
    for c in cands:
        ok, reason = _line_reference_ok(c, th, cfg, query_unit=unit)
        if not ok:
            continue
        sid = c["standard_item_id"]
        if ctx:
            fact, fnote = repo.get_line_fact(sid, ctx)
            if fact:
                note = (
                    f"[知识库整项]{fnote}{scope}「{c['name']}」"
                    f" 名称{c['name_score']:.0%} 特征{c['feature_score']:.0%}"
                )
                return {
                    "material_main": fact.get("material_main") or 0,
                    "material_loss_rate": fact.get("material_loss_rate") or 0,
                    "labor": fact.get("labor") or 0,
                    "material_aux": fact.get("material_aux") or 0,
                    "machinery": fact.get("machinery") or 0,
                }, note
        records = repo.get_cost_records_for_item(sid, ctx=ctx)
        if not records:
            continue
        agg = repo.aggregate_costs(records)
        snote = records[0].get("_scope_note", "") if records else ""
        note = (
            f"[整项参考{c['level']}级]{snote}{scope}「{c['name']}」"
            f" 名称{c['name_score']:.0%} 特征{c['feature_score']:.0%} "
            f"做法{c['tag_score']:.0%}；{c.get('做法摘要', '')}；{len(records)}条样本"
        )
        return {
            "material_main": agg.get("material_main") or 0,
            "material_loss_rate": agg.get("material_loss_rate") or 0,
            "labor": agg.get("labor") or 0,
            "material_aux": agg.get("material_aux") or 0,
            "machinery": agg.get("machinery") or 0,
        }, note

    # 整项参照不成立 → 材料主材价
    mat_cfg = cfg.get("material_fallback", {})
    if not mat_cfg.get("enabled", True):
        why = cands[0] if cands else None
        if why:
            return None, (
                f"无足够相似整项（Top「{why['name']}」名称{why['name_score']:.0%} "
                f"特征{why['feature_score']:.0%}）；{_line_reference_ok(why, th, cfg, query_unit=unit)[1]}"
            )
        return None, "无历史参照"

    lookup = MaterialPriceLookup(repo.db_path)
    mat, note = lookup.find(
        name,
        feature or "",
        unit,
        min_score=mat_cfg.get("min_score", 0.55),
        ctx=ctx,
    )
    if mat and ctx:
        note = f"{note}{scope}"
    if mat:
        return mat, note

    if cands:
        c0 = cands[0]
        return None, (
            f"整项不够相似（{c0['name']} 名称{c0['name_score']:.0%} 特征{c0['feature_score']:.0%}）；{note}"
        )
    return None, note
