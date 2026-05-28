"""人材机分量判断：多源融合 + 分项置信度（目标：资料积累后 ≥80% 可自动判断）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.knowledge.craft_profiles import lookup_craft_profile
from src.knowledge.material_catalog import classify_material_role
from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.normalize.feature_extract import extract_feature_profile
from src.pricing.engine import PricingEngine
from src.pricing.market_reference import lookup_market_reference
from src.pricing.material_lookup import MaterialPriceLookup
from src.pricing.reference_resolve import _line_reference_ok, resolve_reference_costs
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
    if craft_id in ("paint_wall", "paint_ceiling") and u in ("㎡",):
        return 22 <= total <= 95
    if craft_id == "waterproof" and u in ("㎡",):
        return 22 <= total <= 85
    if craft_id in ("tile_floor", "tile_wall") and u in ("㎡",):
        return 80 <= total <= 280
    if craft_id == "generic_finish":
        return False
    return 30 <= total <= 600


def _share_map(template: dict) -> dict:
    return {
        "material_main": template.get("main", template.get("material_main", 0.4)),
        "material_aux": template.get("aux", template.get("material_aux", 0.2)),
        "labor": template.get("labor", 0.36),
        "machinery": template.get("machinery", template.get("machinery", 0.02)),
    }


def _line_match_confidence(cand: dict, cfg: dict) -> float:
    ok, _ = _line_reference_ok(cand, None, cfg)  # type: ignore
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
    min_samples = rules.get("min_profile_samples", 3)

    craft = classify_craft(name, feature, unit)
    prof = extract_feature_profile(feature, name)
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

    # --- 层 1：整项历史 ---
    exclude_ids = {exclude_standard_item_id} if exclude_standard_item_id else None
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
    cands = engine.search(
        name,
        feature or "",
        unit,
        top_n=1,
        exclude_standard_item_ids=exclude_ids,
    )
    line_conf = 0.0
    if comps and cands:
        line_conf = _line_match_confidence(cands[0], cfg)
        if line_conf >= auto_min:
            result.material_main = float(comps.get("material_main") or 0)
            result.material_aux = float(comps.get("material_aux") or 0)
            result.labor = float(comps.get("labor") or 0)
            result.machinery = float(comps.get("machinery") or 0)
            result.material_loss_rate = float(comps.get("material_loss_rate") or 0)
            result.cost_unit_price = (
                result.material_main
                + result.material_aux
                + result.labor
                + result.machinery
            )
            fc = {k: line_conf for k in ("material_main", "material_aux", "labor", "machinery")}
            result.field_confidence = fc
            result.confidence = line_conf
            result.source = "line_match"
            result.notes.append(note)
            result.auto_fill_ok = True
            result.warnings = _validate_expectations(craft, result.as_components(), role)
            return result
        result.notes.append(f"整项参照置信 {line_conf:.0%}<{auto_min:.0%}：{note}")

    # --- 层 2：市场参考价（公开市场/信息价，优先于失真工艺中位数）---
    mkt_city = ctx.city if ctx else ""
    mkt_tier = ctx.price_tier if ctx else "mid"
    market = lookup_market_reference(name, feature, unit, city=mkt_city, tier=mkt_tier)
    if market:
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
        result.auto_fill_ok = market.confidence >= auto_min
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
                result.auto_fill_ok = True
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
                result.auto_fill_ok = True
            result.warnings = _validate_expectations(craft, result.as_components(), role)
            return result

    # --- 层 5：仅整项弱匹配或模板提示 ---
    if comps:
        result.material_main = float(comps.get("material_main") or 0)
        result.material_aux = float(comps.get("material_aux") or 0)
        result.labor = float(comps.get("labor") or 0)
        result.machinery = float(comps.get("machinery") or 0)
        result.material_loss_rate = float(comps.get("material_loss_rate") or 0)
        result.cost_unit_price = (
            result.material_main
            + result.material_aux
            + result.labor
            + result.machinery
        )
        result.confidence = line_conf if cands else 0.55
        result.field_confidence = {k: result.confidence for k in ("material_main", "material_aux", "labor", "machinery")}
        result.source = "line_match_weak"
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
    if judgment.auto_fill_ok or judgment.confidence >= 0.55:
        note = "；".join(
            [f"[判断置信{judgment.confidence:.0%}|{judgment.source}]"]
            + judgment.notes[:2]
        )
        if judgment.warnings:
            note += "；" + "；".join(judgment.warnings[:2])
        return judgment.as_components(), note
    if judgment.confidence >= 0.55 and any(
        judgment.as_components().get(k) for k in ("material_main", "labor")
    ):
        note = f"[参考{judgment.confidence:.0%}|{judgment.source}]" + "；".join(judgment.notes[:1])
        return judgment.as_components(), note
    return None, "；".join(judgment.notes + judgment.warnings)
