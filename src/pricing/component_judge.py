"""人材机分量判断：多源融合 + 分项置信度（目标：资料积累后 ≥80% 可自动判断）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from src.knowledge.craft_profiles import lookup_craft_profile
from src.knowledge.material_catalog import classify_material_role
from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.normalize.feature_extract import extract_feature_profile
from src.pricing.engine import PricingEngine
from src.pricing.cost_basis import get_net_divisor, prefer_net_price
from src.pricing.custom_door import lookup_custom_door_price
from src.pricing.custom_furniture import (
    is_custom_furniture_candidate,
    lookup_custom_furniture_price,
)
from src.pricing.market_reference import lookup_market_reference
from src.pricing.material_lookup import MaterialPriceLookup
from src.pricing.metal_trim import lookup_metal_trim_price
from src.knowledge.cost_split import allocate_by_craft_template, components_usable, share_map
from src.pricing.reconcile import component_total, reconcile_components_with_stored_total
from src.pricing.reference_resolve import _line_reference_ok, _line_reference_ok_strong_name, resolve_reference_costs
from src.pricing.line_identity import (
    auto_fill_requires_feature,
    check_pricing_identity,
    parse_line_identity,
    pricing_basis_note,
)
from src.normalize.text import normalize_unit
from src.normalize.craft_classifier import CraftMatch, classify_craft, get_craft_rules


@dataclass
class ComponentJudgment:
    """单项清单的人材机判断结果。"""
    material_main: float = 0.0
    material_aux: float = 0.0
    labor: float = 0.0
    machinery: float = 0.0
    material_loss_rate: float = 0.0
    cost_unit_price: float = 0.0
    confidence: float = 0.0
    field_confidence: Dict[str, float] = field(default_factory=dict)
    source: str = ""
    craft_type: str = ""
    craft_label: str = ""
    trade: str = ""
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    auto_fill_ok: bool = False

    def as_components(self) -> dict:
        return {
            "material_main": self.material_main,
            "material_loss_rate": self.material_loss_rate,
            "material_aux": self.material_aux,
            "labor": self.labor,
            "machinery": self.machinery,
        }


def _profile_sane(craft_id: str, unit: str, comps: dict) -> bool:
    """工艺价型中位数异常时不用（审计发现 generic 桶误差大）。"""
    total = sum(float(comps.get(k) or 0) for k in ("material_main", "material_aux", "labor", "machinery"))
    if total <= 0 or total > 8000:
        return False
    u = normalize_unit(unit)
    if craft_id in ("paint_wall", "paint_ceiling", "wall_gypsum_paint") and u in ("㎡",):
        return 22 <= total <= 280
    if craft_id == "stone_crystallization" and u in ("㎡",):
        return 35 <= total <= 120
    if craft_id == "waterproof" and u in ("㎡",):
        return 22 <= total <= 85
    if craft_id in ("tile_floor", "tile_wall") and u in ("㎡",):
        return 80 <= total <= 280
    if craft_id == "generic_finish":
        return False
    return 30 <= total <= 600


def _share_map(template: dict) -> dict:
    return share_map(template)


def _allocate_by_craft_template(total: float, craft: CraftMatch) -> dict:
    return allocate_by_craft_template(total, craft)


def _components_usable(comps: Mapping[str, Any]) -> bool:
    return components_usable(comps)


def _line_stored_total(cand: dict, repo: KnowledgeRepository, ctx: Optional[PricingContext]) -> float:
    sid = cand["standard_item_id"]
    if ctx:
        fact, _ = repo.get_line_fact(sid, ctx)
        if fact:
            total = float(fact.get("cost_unit_price") or 0)
            if total > 0:
                return total
    records = repo.get_cost_records_for_item(sid, ctx=ctx)
    if records:
        agg = repo.aggregate_costs(records)
        total = float(agg.get("cost_unit_price") or 0)
        if total > 0:
            return total
        total = float(records[0].get("cost_unit_price") or 0)
        if total > 0:
            return total
    return 0.0


def _line_match_confidence(cand: dict, cfg: dict, *, query_unit: str = "") -> float:
    strong_ok, _ = _line_reference_ok_strong_name(cand, query_unit=query_unit)
    if strong_ok:
        return min(
            0.92,
            max(
                0.8,
                0.35 * cand.get("name_score", 0)
                + 0.45 * cand.get("feature_score", 0)
                + 0.2 * max(cand.get("tag_score", 0), 0.5),
            ),
        )
    ok, _ = _line_reference_ok(cand, None, cfg, query_unit=query_unit)  # type: ignore
    if not ok:
        base = (
            0.25 * cand.get("name_score", 0)
            + 0.35 * cand.get("feature_score", 0)
            + 0.40 * cand.get("tag_score", 0)
        )
        return min(0.79, base)
    return min(
        0.98,
        0.2 * cand.get("name_score", 0)
        + 0.3 * cand.get("feature_score", 0)
        + 0.5 * cand.get("tag_score", 0),
    )


def _validate_expectations(
    craft: CraftMatch,
    comps: dict,
    role_hint: Optional[str],
) -> List[str]:
    warns: List[str] = []
    exp = craft.expects
    total = sum(
        float(comps.get(k) or 0)
        for k in ("material_main", "material_aux", "labor", "machinery")
    )
    if total <= 0:
        warns.append("人材机合计为 0，无法判断")
        return warns
    if exp.get("material_main") and comps.get("material_main", 0) <= 0:
        if role_hint != "辅材":
            warns.append(f"「{craft.label}」通常应有主材，当前主材为 0")
    if exp.get("labor") and comps.get("labor", 0) <= 0:
        warns.append(f"「{craft.label}」通常应有人工费，当前人工为 0")
    if exp.get("material_aux") and comps.get("material_aux", 0) <= 0:
        warns.append(f"「{craft.label}」通常应有辅材，当前辅材为 0")
    return warns


def _component_total(comps: Mapping[str, Any]) -> float:
    return component_total(comps)


def _reconcile_components_with_stored_total(
    comps: dict,
    stored_total: float,
    *,
    threshold: float = 0.92,
    net_divisor: float = 1.0,
    unit: str = "",
    name: str = "",
    feature: str = "",
) -> dict:
    return reconcile_components_with_stored_total(
        comps,
        stored_total,
        threshold=threshold,
        net_divisor=net_divisor,
        unit=unit,
        name=name,
        feature=feature,
    )


def _cost_net_divisor(price_cfg: dict) -> float:
    return get_net_divisor(price_cfg)


def _fact_to_components(
    fact: dict,
    *,
    net_divisor: float = 1.0,
    unit: str = "",
    name: str = "",
    feature: str = "",
) -> dict:
    comps = {
        "material_main": fact.get("material_main") or 0,
        "material_loss_rate": fact.get("material_loss_rate") or 0,
        "labor": fact.get("labor") or 0,
        "material_aux": fact.get("material_aux") or 0,
        "machinery": fact.get("machinery") or 0,
    }
    stored = float(fact.get("cost_unit_price") or 0)
    return _reconcile_components_with_stored_total(
        comps, stored, net_divisor=net_divisor, unit=unit, name=name, feature=feature
    )


def _fetch_line_components_from_candidate(
    cand: dict,
    repo: KnowledgeRepository,
    ctx: Optional[PricingContext],
    cfg: dict,
    *,
    unit: str = "",
    net_divisor: float = 1.0,
    name: str = "",
    feature: str = "",
    craft: Optional[CraftMatch] = None,
) -> Tuple[Optional[dict], str]:
    """弱整项匹配：名称+特征达标时取历史全量人材机（非仅主材价）。"""
    ref = cfg.get("reference_line", {})
    if cand["name_score"] < ref.get("weak_name_min", 0.80):
        return None, ""
    if (cand.get("feature") or "").strip():
        if cand["feature_score"] < ref.get("weak_feature_min", 0.58):
            return None, ""

    def _maybe_split_whole_price(comps: dict, stored: float, note: str) -> Tuple[Optional[dict], str]:
        if _components_usable(comps):
            return _reconcile_components_with_stored_total(
                comps, stored, net_divisor=net_divisor, unit=unit, name=name, feature=feature
            ), note
        if stored <= 0 or craft is None:
            return None, ""
        target = stored
        if net_divisor > 1.0 and prefer_net_price(name, feature, unit):
            target = round(stored / net_divisor, 2)
        split = _allocate_by_craft_template(target, craft)
        return split, f"{note}；整价{stored:.2f}按{craft.label}份额拆分"

    sid = cand["standard_item_id"]
    scope = f"（{ctx.scope_note()}）" if ctx else ""
    if ctx:
        fact, fnote = repo.get_line_fact(sid, ctx)
        if fact:
            stored = float(fact.get("cost_unit_price") or 0)
            comps = {
                "material_main": fact.get("material_main") or 0,
                "material_loss_rate": fact.get("material_loss_rate") or 0,
                "labor": fact.get("labor") or 0,
                "material_aux": fact.get("material_aux") or 0,
                "machinery": fact.get("machinery") or 0,
            }
            note = (
                f"[弱整项{fnote}{scope}「{cand['name']}」"
                f" 名称{cand['name_score']:.0%} 特征{cand['feature_score']:.0%}"
            )
            out, nnote = _maybe_split_whole_price(comps, stored, note)
            if out:
                return out, nnote
    records = repo.get_cost_records_for_item(sid, ctx=ctx)
    if records:
        agg = repo.aggregate_costs(records)
        comps = {
            "material_main": agg.get("material_main") or 0,
            "material_loss_rate": agg.get("material_loss_rate") or 0,
            "labor": agg.get("labor") or 0,
            "material_aux": agg.get("material_aux") or 0,
            "machinery": agg.get("machinery") or 0,
        }
        stored = float(agg.get("cost_unit_price") or agg.get("_cost_unit_price") or 0)
        if stored <= 0 and records:
            stored = float(records[0].get("cost_unit_price") or 0)
        snote = records[0].get("_scope_note", "") if records else ""
        note = (
            f"[弱整项参考]{snote}{scope}「{cand['name']}」"
            f" 名称{cand['name_score']:.0%} 特征{cand['feature_score']:.0%} "
            f"做法{cand['tag_score']:.0%}；{len(records)}条样本"
        )
        out, nnote = _maybe_split_whole_price(comps, stored, note)
        if out:
            return out, nnote
    return None, ""


def _apply_line_components(
    result: ComponentJudgment,
    comps: dict,
    line_conf: float,
    auto_min: float,
    note: str,
    craft: CraftMatch,
    role: Optional[str],
    *,
    name_score: float = 0.0,
    weak_min: float = 0.75,
    weak_name_min: float = 0.8,
    allow_auto: bool = True,
) -> ComponentJudgment:
    result.material_main = float(comps.get("material_main") or 0)
    result.material_aux = float(comps.get("material_aux") or 0)
    result.labor = float(comps.get("labor") or 0)
    result.machinery = float(comps.get("machinery") or 0)
    result.material_loss_rate = float(comps.get("material_loss_rate") or 0)
    result.cost_unit_price = _component_total(result.as_components())
    result.field_confidence = {k: line_conf for k in ("material_main", "material_aux", "labor", "machinery")}
    result.confidence = line_conf
    strong_name = name_score >= weak_name_min
    auto_ok = line_conf >= auto_min or (
        strong_name and line_conf >= weak_min and _components_usable(comps)
    )
    result.source = "line_match" if auto_ok else "line_match_weak"
    result.auto_fill_ok = allow_auto and auto_ok
    result.notes.append(note)
    result.warnings = _validate_expectations(craft, result.as_components(), role)
    return result


def judge_line_components(
    name: str,
    feature: str,
    unit: str,
    engine: PricingEngine,
    repo: KnowledgeRepository,
    *,
    reference_fill: bool = True,
    ctx: Optional[PricingContext] = None,
    exclude_standard_item_id: Optional[int] = None,
) -> ComponentJudgment:
    """
    多源融合判断人材机（置信度 0~1）：
    1. 整项历史匹配（名称+特征+做法）— 最高
    2. 工艺价型库 craft_cost_profiles（同城同档，样本≥3 更稳）
    3. 主材价库 + 工艺份额模板 — 中等
    4. 纯工艺模板（仅结构提示）— 低，不自动填
    """
    rules = get_craft_rules()
    cfg = repo.settings.get("pricing", {})
    judge_cfg = repo.settings.get("component_judge", {})
    auto_min = judge_cfg.get("auto_fill_confidence", rules.get("auto_fill_confidence", 0.8))
    weak_min = judge_cfg.get("weak_line_confidence", 0.75)
    review_min = judge_cfg.get("review_confidence", rules.get("review_confidence", 0.55))
    weak_name_min = cfg.get("reference_line", {}).get("weak_name_min", 0.8)
    net_divisor = _cost_net_divisor(cfg)
    min_samples = rules.get("min_profile_samples", 3)

    craft = classify_craft(name, feature, unit)
    prof = extract_feature_profile(feature, name)
    identity = parse_line_identity(name, feature, unit)
    id_cfg = repo.settings.get("line_identity", {})
    min_feat = int(id_cfg.get("min_feature_chars", 8))

    ok_id, id_reason = check_pricing_identity(
        name,
        feature,
        unit,
        require_unit=id_cfg.get("require_unit", True),
    )
    if not ok_id:
        return ComponentJudgment(
            craft_type=craft.craft_id,
            craft_label=craft.label,
            trade=craft.trade,
            warnings=[id_reason],
            notes=[id_reason],
        )

    feat_ok, feat_reason = auto_fill_requires_feature(
        identity, min_feature_chars=min_feat
    )
    block_auto = id_cfg.get("require_feature_for_auto_fill", True) and not feat_ok

    def _auto(ok: bool) -> bool:
        return ok and not block_auto

    tk, tv = "", ""
    for k in craft.tag_keys:
        if k in prof.tags:
            tk, tv = k, prof.tags[k]
            break

    role, role_note = classify_material_role(name, feature)
    result = ComponentJudgment(
        craft_type=craft.craft_id,
        craft_label=craft.label,
        trade=craft.trade,
    )
    result.notes.append(pricing_basis_note(identity))
    if block_auto:
        result.warnings.append(feat_reason)

    # --- 层 0a：定制柜体（㎡/套）优先于主材编号，避免误套 ST/WD 表价 ---
    if is_custom_furniture_candidate(name, feature, unit):
        furn_early, furn_note = lookup_custom_furniture_price(
            name, feature, unit, repo, ctx, net_divisor=net_divisor
        )
        if furn_early and _components_usable(furn_early):
            result.material_main = float(furn_early.get("material_main") or 0)
            result.material_aux = float(furn_early.get("material_aux") or 0)
            result.labor = float(furn_early.get("labor") or 0)
            result.machinery = float(furn_early.get("machinery") or 0)
            result.material_loss_rate = float(furn_early.get("material_loss_rate") or 0)
            result.cost_unit_price = _component_total(result.as_components())
            result.confidence = 0.85
            result.field_confidence = {k: 0.85 for k in ("material_main", "material_aux", "labor", "machinery")}
            result.source = "custom_furniture_profile"
            result.notes.append(furn_note)
            result.auto_fill_ok = _auto(result.confidence >= auto_min)
            result.warnings = _validate_expectations(craft, result.as_components(), role)
            return result

    # --- 层 0：项目主材编号表（名称/特征含 PT-01、ST-04 → 售楼处主材料价）---
    from src.knowledge.project_materials import extract_material_codes
    from src.pricing.project_material_lookup import lookup_project_material_components

    if extract_material_codes(name, feature):
        proj_comps, proj_note = lookup_project_material_components(
            name, feature, unit, repo, craft, ctx=ctx
        )
        if proj_comps and _components_usable(proj_comps):
            result.material_main = float(proj_comps.get("material_main") or 0)
            result.material_aux = float(proj_comps.get("material_aux") or 0)
            result.labor = float(proj_comps.get("labor") or 0)
            result.machinery = float(proj_comps.get("machinery") or 0)
            result.material_loss_rate = float(proj_comps.get("material_loss_rate") or 0)
            result.cost_unit_price = _component_total(result.as_components())
            result.confidence = 0.88
            result.field_confidence = {
                "material_main": 0.92,
                "material_aux": 0.82,
                "labor": 0.8,
                "machinery": 0.78,
            }
            result.source = "project_material_code"
            result.notes.append(proj_note)
            result.auto_fill_ok = _auto(result.confidence >= auto_min)
            result.warnings = _validate_expectations(craft, result.as_components(), role)
            return result

    # --- 层 1：整项历史 ---
    exclude_ids = {exclude_standard_item_id} if exclude_standard_item_id else None
    cands = engine.search(
        name,
        feature or "",
        unit,
        top_n=3,
        exclude_standard_item_ids=exclude_ids,
    )
    line_conf = _line_match_confidence(cands[0], cfg, query_unit=unit) if cands else 0.0
    comps, note = resolve_reference_costs(
        name,
        feature,
        unit,
        engine,
        repo,
        reference_fill=reference_fill,
        ctx=ctx,
        exclude_standard_item_ids=exclude_ids,
    )
    if comps and cands:
        if line_conf >= auto_min:
            if not _components_usable(comps):
                stored = _line_stored_total(cands[0], repo, ctx)
                if stored > 0:
                    target = stored
                    if net_divisor > 1.0 and prefer_net_price(name, feature, unit):
                        target = round(stored / net_divisor, 2)
                    comps = _allocate_by_craft_template(target, craft)
                    note = f"{note}；整价{stored:.2f}按{craft.label}份额拆分"
            if _components_usable(comps):
                result.material_main = float(comps.get("material_main") or 0)
                result.material_aux = float(comps.get("material_aux") or 0)
                result.labor = float(comps.get("labor") or 0)
                result.machinery = float(comps.get("machinery") or 0)
                result.material_loss_rate = float(comps.get("material_loss_rate") or 0)
                result.cost_unit_price = _component_total(result.as_components())
                fc = {k: line_conf for k in ("material_main", "material_aux", "labor", "machinery")}
                result.field_confidence = fc
                result.confidence = line_conf
                result.source = "line_match"
                result.notes.append(note)
                result.auto_fill_ok = _auto(True)
                result.warnings = _validate_expectations(craft, result.as_components(), role)
                return result
        result.notes.append(f"整项参照置信 {line_conf:.0%}<{auto_min:.0%}：{note}")

    # --- 层 1c：不锈钢/古铜线条按展开面(mm)（优先于弱整项，避免泛化 MT 名称抢价）---
    trim_comps, trim_note = lookup_metal_trim_price(name, feature, unit, repo, ctx)
    if trim_comps and _components_usable(trim_comps):
        result.material_main = float(trim_comps.get("material_main") or 0)
        result.material_aux = float(trim_comps.get("material_aux") or 0)
        result.labor = float(trim_comps.get("labor") or 0)
        result.machinery = float(trim_comps.get("machinery") or 0)
        result.material_loss_rate = float(trim_comps.get("material_loss_rate") or 0)
        result.cost_unit_price = sum(
            float(trim_comps.get(k) or 0)
            for k in ("material_main", "material_aux", "labor", "machinery")
        )
        result.confidence = 0.78
        result.field_confidence = {k: 0.78 for k in ("material_main", "material_aux", "labor", "machinery")}
        result.source = "metal_trim_profile"
        result.notes.append(trim_note)
        result.auto_fill_ok = False
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return result

    # --- 层 1d：定制门/门套（樘）按名称尺寸查价库 ---
    door_comps, door_note = lookup_custom_door_price(name, feature, unit, repo, ctx)
    if door_comps and _components_usable(door_comps):
        result.material_main = float(door_comps.get("material_main") or 0)
        result.material_aux = float(door_comps.get("material_aux") or 0)
        result.labor = float(door_comps.get("labor") or 0)
        result.machinery = float(door_comps.get("machinery") or 0)
        result.material_loss_rate = float(door_comps.get("material_loss_rate") or 0)
        result.cost_unit_price = sum(
            float(door_comps.get(k) or 0)
            for k in ("material_main", "material_aux", "labor", "machinery")
        )
        result.confidence = 0.82
        result.field_confidence = {k: 0.82 for k in ("material_main", "material_aux", "labor", "machinery")}
        result.source = "custom_door_profile"
        result.notes.append(door_note)
        result.auto_fill_ok = False
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return result

    # --- 层 1e：定制家具/吧台（套）按尺寸查价库 ---
    furn_comps, furn_note = lookup_custom_furniture_price(
        name, feature, unit, repo, ctx, net_divisor=net_divisor
    )
    if furn_comps and _components_usable(furn_comps):
        result.material_main = float(furn_comps.get("material_main") or 0)
        result.material_aux = float(furn_comps.get("material_aux") or 0)
        result.labor = float(furn_comps.get("labor") or 0)
        result.machinery = float(furn_comps.get("machinery") or 0)
        result.material_loss_rate = float(furn_comps.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        result.confidence = 0.82
        result.field_confidence = {k: 0.82 for k in ("material_main", "material_aux", "labor", "machinery")}
        result.source = "custom_furniture_profile"
        result.notes.append(furn_note)
        result.auto_fill_ok = False
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return result

    # --- 层 1b：弱整项（≥75% 或名称强命中）取历史全量人材机 ---
    mkt_city = ctx.city if ctx else ""
    mkt_tier = ctx.price_tier if ctx else "mid"
    market = lookup_market_reference(name, feature, unit, city=mkt_city, tier=mkt_tier)

    if cands:
        weak_comps, weak_note = _fetch_line_components_from_candidate(
            cands[0], repo, ctx, cfg,
            unit=unit, net_divisor=net_divisor, name=name, feature=feature, craft=craft,
        )
        name_ok = cands[0].get("name_score", 0) >= weak_name_min
        if weak_comps and (line_conf >= weak_min or (name_ok and line_conf >= review_min)):
            # 仅当整项置信低于 review 且有市场参考时，让市场价优先
            prefer_market = bool(market and line_conf < review_min)
            if not prefer_market:
                return _apply_line_components(
                    result, weak_comps, line_conf, auto_min, weak_note, craft, role,
                    name_score=cands[0].get("name_score", 0),
                    weak_min=weak_min,
                    weak_name_min=weak_name_min,
                    allow_auto=not block_auto,
                )

    # --- 层 1f：涂料工序拆价（优先于平面市场参考价）---
    from src.pricing.material_process_price import PAINT_CRAFT_IDS, lookup_paint_by_feature

    paint_market_rules = {
        "wall_gypsum_paint",
        "wall_paint_plaster",
        "paint_ceiling",
        "paint_ceiling_waterproof",
    }
    paint_tier = ctx.price_tier if ctx else "mid"
    use_paint_process = craft.craft_id in PAINT_CRAFT_IDS or bool(
        market and market.rule_id in paint_market_rules
    )
    if use_paint_process:
        proc_comps, proc_note = lookup_paint_by_feature(
            name, feature, unit, craft_id=craft.craft_id, price_tier=paint_tier
        )
        if proc_comps and _components_usable(proc_comps):
            result.material_main = float(proc_comps.get("material_main") or 0)
            result.material_aux = float(proc_comps.get("material_aux") or 0)
            result.labor = float(proc_comps.get("labor") or 0)
            result.machinery = float(proc_comps.get("machinery") or 0)
            result.material_loss_rate = float(proc_comps.get("material_loss_rate") or 0)
            result.cost_unit_price = _component_total(result.as_components())
            result.confidence = 0.84
            result.field_confidence = {
                "material_main": 0.85,
                "material_aux": 0.82,
                "labor": 0.83,
                "machinery": 0.78,
            }
            result.source = "paint_process"
            result.notes.append(proc_note)
            result.auto_fill_ok = _auto(result.confidence >= auto_min)
            result.warnings = _validate_expectations(craft, result.as_components(), role)
            return result

    # --- 层 2：市场参考价（须名称+特征+单位均达标，禁止无特征平面套价）---
    if market and not block_auto:
        result.material_main = market.material_main
        result.material_aux = market.material_aux
        result.labor = market.labor
        result.machinery = market.machinery
        result.material_loss_rate = market.material_loss_rate
        result.cost_unit_price = (
            market.material_main
            + market.material_aux
            + market.labor
            + market.machinery
        )
        result.field_confidence = {k: market.confidence for k in ("material_main", "material_aux", "labor", "machinery")}
        result.confidence = market.confidence
        result.source = "market_reference"
        scope = ctx.scope_note() if ctx else ""
        result.notes.append(f"[市场参考{scope}] {market.note}（规则:{market.rule_id}）")
        result.auto_fill_ok = _auto(market.confidence >= auto_min)
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return result

    # --- 层 3：工艺价型库 ---
    conn = repo.conn()
    try:
        profile = lookup_craft_profile(
            conn, craft.craft_id, unit, tag_key=tk, tag_value=tv, ctx=ctx
        )
    finally:
        conn.close()

    profile_conf = 0.0
    if profile and craft.craft_id != "generic_finish":
        n = int(profile.get("sample_count") or 0)
        profile_conf = min(float(profile.get("confidence_base") or 0.5), 0.74)
        if n < min_samples:
            profile_conf = min(profile_conf, 0.65)
        pm = float(profile.get("material_main") or 0)
        pa = float(profile.get("material_aux") or 0)
        pl = float(profile.get("labor") or 0)
        pmc = float(profile.get("machinery") or 0)
        prof_comps = {
            "material_main": pm,
            "material_aux": pa,
            "labor": pl,
            "machinery": pmc,
        }
        if n >= min_samples and _profile_sane(craft.craft_id, unit, prof_comps):
            result.material_main = pm
            result.material_aux = pa
            result.labor = pl
            result.machinery = pmc
            result.material_loss_rate = float(profile.get("material_loss_rate") or 0)
            result.cost_unit_price = float(profile.get("cost_unit_price") or 0) or (
                pm + pa + pl + pmc
            )
            result.field_confidence = {
                k: profile_conf for k in ("material_main", "material_aux", "labor", "machinery")
            }
            result.confidence = profile_conf
            result.source = "craft_profile"
            scope = ctx.scope_note() if ctx else ""
            result.notes.append(
                f"[工艺价型]{craft.label}{scope} 样本{n} 标签{tk}={tv or '—'}"
            )
            if profile_conf >= auto_min:
                result.auto_fill_ok = _auto(True)
                result.warnings = _validate_expectations(craft, result.as_components(), role)
                return result
            result.notes.append(f"工艺价型置信 {profile_conf:.0%}，建议人工复核")
        else:
            result.notes.append(
                f"工艺价型样本{n}未通过合理性校验或归类为「装饰综合」，已跳过"
            )

    # --- 层 4：主材价库 + 份额模板 ---
    lookup = MaterialPriceLookup(repo.db_path)
    mat, mnote = lookup.find(name, feature or "", unit, ctx=ctx)
    shares = _share_map(craft.template_share)
    hybrid_conf = 0.0

    if mat and mat.get("material_main", 0) > 0:
        if craft.craft_id == "stone_crystallization":
            result.notes.append("石材晶面/结晶项跳过主材价库+铺贴模板")
        else:
            main_val = float(mat["material_main"])
            main_share = shares["material_main"]
            if main_share > 0.05:
                total_est = main_val / main_share
                result.material_main = main_val
                result.material_loss_rate = float(mat.get("material_loss_rate") or 0)
                result.material_aux = round(total_est * shares["material_aux"], 2)
                result.labor = round(total_est * shares["labor"], 2)
                result.machinery = round(total_est * shares["machinery"], 2)
                result.cost_unit_price = round(total_est, 2)
                hybrid_conf = 0.68 + 0.08 * (1 if profile else 0) + 0.05 * (1 if role else 0)
                result.field_confidence = {
                    "material_main": 0.82,
                    "material_aux": hybrid_conf - 0.12,
                    "labor": hybrid_conf - 0.08,
                    "machinery": hybrid_conf - 0.15,
                }
                result.confidence = min(hybrid_conf, min(result.field_confidence.values()))
                result.source = "material_plus_template"
                result.notes.append(mnote)
                result.notes.append(
                    f"按「{craft.label}」份额模板推算辅材/人工（主材来自价库）"
                )
                if role:
                    result.notes.append(role_note)
                if hybrid_conf >= auto_min - 0.02:
                    result.auto_fill_ok = _auto(True)
                result.warnings = _validate_expectations(craft, result.as_components(), role)
                return result

    # --- 层 5：仅整项弱匹配或模板提示 ---
    if comps:
        if not _components_usable(comps) and cands:
            stored = _line_stored_total(cands[0], repo, ctx)
            if stored > 0 and craft:
                target = stored
                if net_divisor > 1.0 and prefer_net_price(name, feature, unit):
                    target = round(stored / net_divisor, 2)
                comps = _allocate_by_craft_template(target, craft)
                note = (note or "弱匹配整项") + f"；整价{stored:.2f}按{craft.label}份额拆分"
        result.material_main = float(comps.get("material_main") or 0)
        result.material_aux = float(comps.get("material_aux") or 0)
        result.labor = float(comps.get("labor") or 0)
        result.machinery = float(comps.get("machinery") or 0)
        result.material_loss_rate = float(comps.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        result.confidence = line_conf if cands else 0.55
        result.field_confidence = {k: result.confidence for k in ("material_main", "material_aux", "labor", "machinery")}
        usable = _components_usable(comps)
        strong_name = cands and cands[0].get("name_score", 0) >= weak_name_min
        auto_ok = (
            line_conf >= auto_min
            or (usable and strong_name and line_conf >= weak_min)
            or (usable and line_conf >= review_min)
        )
        result.source = "line_match" if auto_ok else "line_match_weak"
        result.auto_fill_ok = _auto(auto_ok)
        result.notes.append(note or "弱匹配整项，建议人工核对")
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return result

    result.confidence = 0.35
    result.source = "unresolved"
    result.notes.append(
        f"未达自动判断门槛：工艺={craft.label}；{role_note if role else '无材料目录命中'}"
    )
    if profile:
        result.notes.append(
            f"有工艺价型样本{profile.get('sample_count')}条但置信不足，可执行 backfill-kb 重建价型库"
        )
    result.warnings = ["需人工组价或补充历史资料"]
    return result


def judge_to_reference_tuple(
    judgment: ComponentJudgment,
) -> Tuple[Optional[dict], str]:
    """供 inplace_bidder / reference_resolve 使用的 (components, note)。"""
    rules = get_craft_rules()
    review_min = rules.get("review_confidence", 0.55)
    comps = judgment.as_components()
    note_parts = judgment.notes + judgment.warnings

    if judgment.source == "material_plus_template" and judgment.craft_type == "stone_crystallization":
        return None, "；".join(note_parts)

    if not _components_usable(comps):
        return None, "；".join(note_parts)

    if judgment.auto_fill_ok or judgment.confidence >= review_min:
        note = "；".join(
            [f"[判断置信{judgment.confidence:.0%}|{judgment.source}]"]
            + judgment.notes[:2]
        )
        if judgment.warnings:
            note += "；" + "；".join(judgment.warnings[:2])
        return comps, note
    return None, "；".join(note_parts)
