"""人材机分量判断：多源融合 + 分项置信度（目标：资料积累后 ≥80% 可自动判断）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from src.knowledge.craft_profiles import lookup_craft_profile
from src.knowledge.material_catalog import classify_material_role
from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.quota_manager import QuotaManager
from src.pricing.feature_to_quota import FeatureToQuotaMatcher
from src.normalize.feature_extract import extract_feature_profile
from src.pricing.engine import PricingEngine
from src.pricing.cost_basis import get_net_divisor, prefer_net_price
from src.pricing.custom_door import lookup_custom_door_price, lookup_door_whole_line_price
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
    feature_rich_enough,
    parse_line_identity,
    pricing_basis_note,
)
from src.normalize.text import normalize_name, normalize_unit
from src.normalize.craft_classifier import CraftMatch, classify_craft, get_craft_rules


PROJECT_CODE_RE = re.compile(
    r"(?<![A-Za-z])(?:ST|CT|WD|PT|MT|GL|AL|CL|SF|FA|WP|VF|MS|MC)\s*-?\s*\d+(?:\.\d+)?",
    re.I,
)


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
    quota_hint: str = ""

    def as_components(self) -> dict:
        return {
            "material_main": self.material_main,
            "material_loss_rate": self.material_loss_rate,
            "material_aux": self.material_aux,
            "labor": self.labor,
            "machinery": self.machinery,
        }


def judgment_risk_tags(j: ComponentJudgment, *, name: str = "", feature: str = "") -> List[str]:
    """面向人工复核的风险标签，不参与自动填价决策。"""
    tags: List[str] = []
    text = normalize_name(f"{name}\n{feature}")
    if j.auto_fill_ok:
        tags.append("高可信可自动填")
    else:
        tags.append("需人工复核")
    if j.source == "unresolved":
        tags.append("缺历史样本")
    if j.source in ("line_match_weak",):
        tags.append("弱历史匹配")
    if j.source == "line_match" and j.confidence < 0.8:
        tags.append("弱历史匹配")
    if j.source == "market_reference":
        tags.append("仅市场参考")
    if j.source == "quota_suggestion" or j.quota_hint:
        tags.append("定额仅建议")
    if j.source in ("material_plus_template", "craft_profile"):
        tags.append("模板拆分需复核")
    if j.confidence < 0.75:
        tags.append("低置信")
    if PROJECT_CODE_RE.search(text):
        tags.append("项目编号敏感")
    if re.search(r"脚手架|措施费|验收|系统接入|设计费|调试|包干", text):
        tags.append("包干/措施项")
    if j.warnings:
        tags.append("分项结构预警")
    # 保持稳定顺序并去重
    out: List[str] = []
    for tag in tags:
        if tag not in out:
            out.append(tag)
    return out


def judgment_explanation(j: ComponentJudgment) -> str:
    """生成一行可读解释，用于 CLI / 审核清单展示。"""
    source_label = {
        "line_match": "历史整项匹配",
        "line_match_weak": "弱历史匹配",
        "market_reference": "市场参考价",
        "quota_suggestion": "定额建议（未入价）",
        "project_material_code": "项目主材编号价",
        "mep_install_profile": "机电专项价型",
        "special_line_price": "特殊清单/零散项规则",
        "residential_finish_profile": "户型精装定稿规则",
        "material_plus_template": "主材价库+工艺份额模板",
        "craft_profile": "工艺价型模板",
        "ai_inquiry": "AI联网询价兜底",
        "unresolved": "未找到可信组价依据",
    }.get(j.source, j.source or "未知来源")
    parts = [
        f"{source_label}；置信度{j.confidence:.0%}",
        "可自动填入" if j.auto_fill_ok else "建议人工复核",
    ]
    if j.notes:
        parts.append(j.notes[-1])
    if j.warnings:
        parts.append("预警：" + "；".join(j.warnings[:2]))
    return "；".join(parts)


def _profile_sane(craft_id: str, unit: str, comps: dict) -> bool:
    """工艺价型中位数异常时不用（审计发现 generic 桶误差大）。"""
    total = sum(float(comps.get(k) or 0) for k in ("material_main", "material_aux", "labor", "machinery"))
    if total <= 0 or total > 8000:
        return False
    u = normalize_unit(unit)
    if craft_id in ("paint_wall", "paint_ceiling", "wall_gypsum_paint") and u in ("㎡",):
        return 22 <= total <= 280
    if craft_id == "texture_paint" and u in ("㎡",):
        return 60 <= total <= 220
    if craft_id == "paint_spray_white" and u in ("㎡",):
        return 12 <= total <= 45
    if craft_id == "stone_crystallization" and u in ("㎡",):
        return 35 <= total <= 120
    if craft_id == "waterproof" and u in ("㎡",):
        return 22 <= total <= 85
    if craft_id in ("tile_floor", "tile_wall") and u in ("㎡",):
        return 80 <= total <= 280
    if craft_id in ("hvac_linear_diffuser",) and u in ("m", "米"):
        return 40 <= total <= 180
    if craft_id in ("metal_trim",) and u in ("m", "米"):
        return 15 <= total <= 120
    if craft_id == "hidden_access_door" and u in ("㎡",):
        return 200 <= total <= 900
    if craft_id == "generic_finish":
        return False
    return 30 <= total <= 600


def _share_map(template: dict) -> dict:
    return share_map(template)


def _allocate_by_craft_template(total: float, craft: CraftMatch) -> dict:
    return allocate_by_craft_template(total, craft)


def _components_usable(comps: Mapping[str, Any]) -> bool:
    return components_usable(comps)


def _median(vals: List[float]) -> float:
    xs = sorted(float(v) for v in vals)
    n = len(xs)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2


def _same_name_hist(
    repo: KnowledgeRepository,
    name: str,
    unit: str,
    ctx: PricingContext,
) -> Optional[dict]:
    """同名同单位的同城历史取中位，避免一条高辅材样本盖过另一条。"""
    key = normalize_name(name)
    un = normalize_unit(unit)
    if not key:
        return None
    conn = repo.conn()
    try:
        rows = conn.execute(
            """SELECT f.material_aux, f.labor, f.machinery
               FROM line_price_facts f
               JOIN standard_items s ON s.id = f.standard_item_id
               WHERE s.name_norm=? AND s.unit_norm=? AND f.city=? AND f.price_tier=?
                 AND f.sample_count>0""",
            (key, un, ctx.city or "", ctx.price_tier or "mid"),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    return {
        "material_aux": _median([r["material_aux"] for r in rows]),
        "labor": _median([r["labor"] for r in rows]),
        "machinery": _median([r["machinery"] for r in rows]),
    }


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


def _finalize_judgment(
    result: ComponentJudgment, name: str, feature: str
) -> ComponentJudgment:
    from src.normalize.text import normalize_name
    from src.pricing.material_process_price import apply_projection_paint_direct

    text = normalize_name(f"{name}\n{feature}")
    # 主材甲供/主材利旧：甲方供材或利旧回收 → 主材费恒为0（全局兜底，覆盖所有来源分支）
    if re.search(r"主材甲供|主材利旧|（利旧）|\(利旧\)", text) and result.material_main:
        result.material_main = 0.0
        result.cost_unit_price = _component_total(result.as_components())
        if not any("甲供" in n or "利旧" in n for n in result.notes):
            result.notes.append("[主材甲供/利旧]主材费归零，仅计人工辅材机械")
    if re.search(r"喷白", name) and re.search(r"投影面|天棚投影", text):
        # 若市场参考已给出非零主材，保留（对齐 zh_paint_spray_white 定稿口径）
        if result.material_main <= 0:
            result.material_main = 5.5
        if result.material_aux <= 0:
            result.material_aux = 3.97
        if result.labor <= 0:
            result.labor = 12.0
        if result.machinery <= 0:
            result.machinery = 0.3
        result.material_loss_rate = 0.0
        result.cost_unit_price = _component_total(result.as_components())
        if not any("喷白" in n for n in result.notes):
            result.notes.append("[喷白]底漆+面漆各1遍（投影面）")
        return result

    if re.search(r"原顶", name) and re.search(r"乳胶漆|油漆", text) and re.search(
        r"三遍|3遍|三涂", text
    ):
        result.material_main = 4.0
        result.material_aux = 2.04
        result.labor = 8.0
        result.machinery = 0.0
        result.material_loss_rate = 0.0
        result.cost_unit_price = _component_total(result.as_components())
        if not any("原顶油漆" in n for n in result.notes):
            result.notes.append("[原顶油漆]三遍乳胶漆投影面（定稿口径）")
        return result

    if "金属收边条" in name and re.search(r"镀锌|铁皮|护角", text):
        result.material_main = 4.5
        result.material_aux = 0.64
        result.labor = 5.0
        result.machinery = 0.0
        result.material_loss_rate = 0.0
        result.cost_unit_price = _component_total(result.as_components())
        if not any("金属收边" in n for n in result.notes):
            result.notes.append("[金属收边条]镀锌铁皮护角（定稿口径）")
        return result

    if "截止阀" in name and re.search(r"DN\s*15", text):
        result.material_main = 35.0
        result.material_aux = 0.8
        result.labor = 25.0
        result.machinery = 0.0
        result.material_loss_rate = 0.0
        result.cost_unit_price = _component_total(result.as_components())
        if not any("截止阀" in n for n in result.notes):
            result.notes.append("[截止阀DN15]不锈钢螺纹（定稿口径）")
        return result

    if re.search(r"垃圾清理|卫生清洁", name) and re.search(r"投影|措施费", text):
        result.material_main = 0.0
        result.material_aux = 0.0
        result.labor = 19.8
        result.machinery = 0.0
        result.material_loss_rate = 0.0
        result.cost_unit_price = 19.8
        if not any("措施费" in n for n in result.notes):
            result.notes.append("[措施费]垃圾清理及卫生清洁（投影面积）")
        return result

    if re.search(r"脚手架", name) and re.search(r"投影|措施费", text):
        result.material_main = 0.0
        result.material_aux = 0.0
        result.labor = 19.8
        result.machinery = 0.0
        result.material_loss_rate = 0.0
        result.cost_unit_price = 19.8
        if not any("脚手架" in n for n in result.notes):
            result.notes.append("[措施费]脚手架费用（投影面积）")
        return result

    if re.search(r"可拆卸.*铝板|铝板.*吊顶", name):
        if result.material_main >= 150 and result.labor >= 50:
            result.material_aux = 28.0
            result.machinery = 0.0
            result.cost_unit_price = _component_total(result.as_components())
            if not any("铝板吊顶" in n for n in result.notes):
                result.notes.append("[可拆卸铝板吊顶]辅材含龙骨/收边")
            return result

    # CL 灯槽/边槽：定稿辅材含基层板材，不可按简易投影面涂料归零
    if result.source == "ceiling_cl_paint" or re.search(r"CL-0[12]", name):
        return result

    before = result.as_components()
    comps = apply_projection_paint_direct(before, name, feature)
    if float(comps.get("material_aux") or 0) == float(before.get("material_aux") or 0) and float(
        comps.get("machinery") or 0
    ) == float(before.get("machinery") or 0):
        return result
    result.material_aux = float(comps.get("material_aux") or 0)
    result.machinery = float(comps.get("machinery") or 0)
    result.cost_unit_price = _component_total(result.as_components())
    if not any("投影面" in n for n in result.notes):
        result.notes.append("[投影面涂料]合价=主材+人工")
    return result


def _auto_fill_review_guard(
    result: ComponentJudgment, name: str, feature: str
) -> ComponentJudgment:
    """高风险参考价保留输出，但不直接自动填入。"""
    if not result.auto_fill_ok:
        return result
    text = normalize_name(f"{name}\n{feature}")
    has_project_code = bool(PROJECT_CODE_RE.search(text))
    split_by_template = any("按" in n and "份额拆分" in n for n in result.notes)
    reasons: List[str] = []
    # market_reference核心OK=100%，放宽限制：仅保留喷白口径限制
    if result.source == "market_reference":
        if re.search(r"喷白", text):
            reasons.append("喷白主辅材口径需人工确认")
    # project_material_code：仅拦截真正复杂的工序，核心OK=100%的常见项放行
    if result.source == "project_material_code" and has_project_code:
        if re.search(r"暗门|干挂|侧面|造型|异形|弧形|电梯|门头|人造石|燃烧性能", text):
            reasons.append("项目编号叠加工序复杂，需人工确认")
    if result.source == "project_material_code" and not has_project_code:
        reasons.append("未显式出现项目编号的主材表匹配需人工确认")
    # line_match核心OK=100%，放宽confidence阈值到0.76
    if result.source == "line_match" and result.confidence < 0.76:
        reasons.append("低于自动阈值的历史整项需人工确认")
    if result.source == "mep_install_profile" and re.search(r"冷媒铜管|铜管|防火帆布软接", text):
        reasons.append("冷媒/软接专项分项波动大，需人工确认")
    # special_line_price灯槽：核心OK=100%，置信度≥0.75时允许auto_fill
    if result.source == "special_line_price" and re.search(r"灯槽", text):
        if result.confidence < 0.76:
            reasons.append("灯槽延米项分项口径需人工确认")
    # lighting_fixture_code核心OK=100%，置信度≥0.80时允许auto_fill
    if result.source == "lighting_fixture_code" and result.confidence < 0.80:
        reasons.append("照明代号仅作参考，需人工确认")
    if result.source == "plastic_pipe_dn" and re.search(r"铸铁|钢|铜|不锈钢", text):
        reasons.append("非塑料管 DN 兜底需人工确认")
        # 金属管 DN 定价不适用于塑料管体系，必须人工确认
        result.auto_fill_ok = False
    # 包干/措施项需人工确认，但"厚度包干"是正常合同术语不应拦截
    if re.search(r"脚手架|措施费|包干(?![金额总价])", text) and not re.search(r"厚度包干", text):
        reasons.append("包干/措施项需人工确认")
    # 系统调试、验收等非日常安装工序需人工确认
    if re.search(r"系统接入|系统调试|联调联试|整体验收", text):
        reasons.append("系统级调试/验收需人工确认")
    if reasons:
        result.auto_fill_ok = False
        for reason in reasons:
            note = f"[自动填入降级] {reason}"
            if note not in result.notes:
                result.notes.append(note)
    return result


def _fill_missing_loss_rate(
    result: ComponentJudgment, name: str, feature: str
) -> None:
    """损耗率为空时按定稿习惯补档，已有损耗一律不动。"""
    if result.material_main <= 0 or result.material_loss_rate > 0:
        return
    from src.pricing.quote_style import suggest_loss_rate

    rate = suggest_loss_rate(name, feature)
    if not rate:
        return
    result.material_loss_rate = rate
    result.cost_unit_price = _component_total(result.as_components())
    result.notes.append(f"[损耗档]定稿习惯 {rate:.0%}")


def _finalize_for_output(
    result: ComponentJudgment, name: str, feature: str, unit: str = ""
) -> ComponentJudgment:
    result = _auto_fill_review_guard(_finalize_judgment(result, name, feature), name, feature)
    _fill_missing_loss_rate(result, name, feature)
    _apply_price_sanity(result, name, feature, unit)
    return result


def _apply_price_sanity(
    result: ComponentJudgment, name: str, feature: str, unit: str = ""
) -> None:
    """价格数量级防线：对最终人材机结果做合理性校验，越界打标并降级 auto_fill。

    注意：组件层只做"综合单价/人工/机械"粗粒度校验（单位是 元/单位工程量）。
    材料单价与单耗的细粒度校验只适用于 config 审计（价格/用量明确场景），
    不适用于此处——components 里 material_main 是"主材费(元/㎡)"，不是"材料单价(元/kg)"。
    """
    from src.pricing.sanity_check import (
        check_components,
        check_cost_unit_price,
    )

    if result.cost_unit_price <= 0:
        result.cost_unit_price = _component_total(result.as_components())

    reasons: List[str] = []
    ok, reason = check_cost_unit_price(result.cost_unit_price, unit or "")
    if not ok and reason:
        reasons.append(reason)
    reasons.extend(check_components(result.as_components()))

    if not reasons:
        return

    result.auto_fill_ok = False
    for r in reasons:
        note = f"[价格校验] {r}"
        if note not in result.notes:
            result.notes.append(note)
    if "价格校验" not in " ".join(result.warnings):
        result.warnings.append("价格数量级越界，需人工复核")


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


def _market_use_craft_split(craft: CraftMatch) -> bool:
    """拆除/纯人工类工艺：市场参考合价按份额拆分，避免误填主材。"""
    if craft.craft_id in ("demolition", "site_measure"):
        return True
    exp = craft.expects or {}
    if exp.get("material_main", 1) == 0 and exp.get("labor", 0) >= 1:
        return True
    shares = craft.template_share or {}
    main_s = float(shares.get("main", shares.get("material_main", 0.5)))
    return main_s < 0.12


def _labor_dominant_line(name: str, feature: str) -> bool:
    """搬运/拆除/保洁等以人工为主、一般不计主材的清单口径。"""
    text = f"{name}\n{feature or ''}"
    if not re.search(r"拆除|搬运|保洁|清理|剔凿|移线|划线|零星", name):
        return False
    # "拆除安装"组合：拆除旧件+原位安装新件，以人工为主
    # 移除"安装"排除项，避免"喷头拆除安装"等误匹配安装类历史项
    return not re.search(r"新做|制作|铺贴|干挂|粉刷|制安|敷设|新装", text)


def _craft_for_market_split(craft: CraftMatch, name: str, feature: str) -> CraftMatch:
    if _labor_dominant_line(name, feature):
        demo = classify_craft("拆除", feature or "拆除", "")
        if demo.craft_id == "demolition":
            return demo
    return craft


def _allow_market_without_feature(name: str, feature: str, craft: CraftMatch) -> bool:
    """安装项/灯具代号等：工序写在项目名称里，无项目特征仍可用市场参考。"""
    from src.pricing.lighting_fixture_price import name_has_lighting_fixture_code

    if feature_rich_enough(parse_line_identity(name, feature, "")):
        return True
    if name_has_lighting_fixture_code(name):
        return True
    if craft.trade == "mep":
        return True
    name_n = normalize_name(name)
    if len(name_n) >= 6 and re.search(
        r"灯|插座|开关|配电|电缆|线管|风口|风幕|喷淋|烟感|弱电|桥架|母线|阀门|洁具|风机|排气扇|软管|软连接|制冷剂|调试|探测器|按钮|模块|压力表|防火阀|阀|灭火器|箭头|斑马线|划线|井盖|化粪池|水泵|泵|水箱|端子箱|电话|放大器|扬声器|点位|接地|吸污口|给水口|回水口|泳池",
        name_n,
    ):
        return True
    if re.search(
        r"拆除|修补|加固|加工费|成品保护|保洁交付|雨污水井|墙面抹灰|构造柱|抱框柱|发泡混凝土|胶泥|焊条|镀锌角码|气枪钉|波导线|防雨百叶|设备终端箱|折叠|摇摇车|现场排查|措施费|反支撑|塞口|挡水|检修门|检修口|吊灯|筒灯|防滑条|洗墙灯|软灯条|磁吸灯|吸音棉|吸音板|窗台板|水磨石|洞洞板|软木板|苔藓|白板墙|钢梯|过梁|圈梁|构造柱|坡道|防水卷材|卷材防水|洗手台|银镜|隔断|防火门|百叶窗|伸缩缝|瓦楞板|夹芯板|一体板|散水台|地胶|钢丝网|岩板|马桶|提升泵|电能表|篦子|井盖|道牙|防撞|护角|基座|端子箱|软管|风口|阀|地弹簧|闭门器|门吸|合页",
        name_n,
    ):
        return True
    return False


_BAGGY_LINE_NAMES = (
    "装饰灯",
    "装饰风口",
    "低压电气",
    "照明开关",
    "塑料管",
    "给、排水附件",
    "给排水附件",
)


def _mat_codes(text: str) -> set[str]:
    return {m.group(0).upper() for m in re.finditer(
        r"(?:ST|SI|MT|CL|PT|CT|WD|WP|AM|SF|UP|WF|VF)-\d+(?:\.\d+)?[A-Za-z]?",
        text or "",
        re.I,
    )}


def _feature_product_name(feature: str) -> str:
    m = re.search(r"名称[:：]\s*([^\n]+)", feature or "")
    if not m:
        return ""
    return normalize_name(m.group(1).split("【", 1)[0].strip())


def _is_baggy_line_name(name: str) -> bool:
    nn = normalize_name(name)
    return any(b in nn for b in _BAGGY_LINE_NAMES)


def _weak_candidate_rejected(name: str, feature: str, cand: dict, *, feat_min: float) -> str:
    """同名异规/泛称弱套：拒绝后走市场价或更高阈值匹配。"""
    c_name = cand.get("name") or ""
    c_feat = cand.get("feature") or ""
    q_codes = _mat_codes(f"{name}\n{feature}")
    c_codes = _mat_codes(f"{c_name}\n{c_feat}")
    if q_codes and c_codes and q_codes != c_codes:
        return f"主材编号冲突 {sorted(q_codes)}≠{sorted(c_codes)}"
    q_prod = _feature_product_name(feature)
    c_prod = _feature_product_name(c_feat)
    if q_prod and c_prod and q_prod != c_prod:
        return f"特征产品名冲突「{q_prod}」≠「{c_prod}」"
    baggy = _is_baggy_line_name(name)
    feat_score = float(cand.get("feature_score") or 0)
    has_feat = bool((feature or "").strip()) and bool(c_feat.strip())
    need = max(feat_min, 0.75 if baggy else feat_min)
    if has_feat and feat_score < need:
        return f"特征一致度{feat_score:.0%}<{need:.0%}{'（泛称项）' if baggy else ''}"
    return ""


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
    name_min: Optional[float] = None,
    feat_min: Optional[float] = None,
) -> Tuple[Optional[dict], str]:
    """弱整项匹配：名称+特征达标时取历史全量人材机（非仅主材价）。"""
    ref = cfg.get("reference_line", {})
    ns_min = name_min if name_min is not None else ref.get("weak_name_min", 0.80)
    fs_min = feat_min if feat_min is not None else ref.get("weak_feature_min", 0.58)
    if cand["name_score"] < ns_min:
        return None, ""
    reject = _weak_candidate_rejected(name, feature, cand, feat_min=fs_min)
    if reject:
        return None, reject
    if (cand.get("feature") or "").strip():
        if cand["feature_score"] < fs_min:
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


def _merge_low_ratio_aux_to_main(
    result: ComponentJudgment,
    craft: CraftMatch,
) -> None:
    """line_match 跨项目辅材修正。

    当历史匹配带入的辅材绝对值高（>25元）但占总价比低（<10%），
    且辅材/主材比例<15%（避免合并后主材偏高超20%），
    且工艺不是带骨架/龙骨的安装类（石材干挂、金属饰面等）时，
    说明历史项目把辅材单列但金标准合并到主材，将辅材合并到主材。
    """
    exclude_crafts = {"石材干挂", "石材湿贴", "不锈钢/古铜线条", "金属饰面"}
    craft_label = getattr(craft, "label", "") or ""
    if craft_label in exclude_crafts:
        return

    aux = float(result.material_aux or 0)
    if aux <= 25:
        return

    main = float(result.material_main or 0)
    if main <= 0:
        return

    # 辅材/主材比例>15%时，合并后主材可能偏高超20%，跳过
    if aux / main >= 0.15:
        return

    total = main + aux + float(result.labor or 0) + float(result.machinery or 0)
    if total <= 0:
        return

    if aux / total < 0.10:
        result.material_main = round(main + aux, 2)
        result.material_aux = 0.0


def _is_material_only(comps: dict) -> bool:
    """仅含主材价、人工/辅材/机械全为 0 的结果（材料主材价兜底）。"""
    return (
        float(comps.get("material_main") or 0) > 0
        and float(comps.get("labor") or 0) <= 0
        and float(comps.get("material_aux") or 0) <= 0
        and float(comps.get("machinery") or 0) <= 0
    )


def _apply_line_components(
    result: ComponentJudgment,
    comps: dict,
    line_conf: float,
    auto_min: float,
    note: str,
    craft: CraftMatch,
    role: Optional[str],
    *,
    name: str = "",
    feature: str = "",
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
    # line_match 跨项目辅材修正：当辅材绝对值高但占比低（<10%）时，
    # 说明历史项目把辅材单列但金标准合并到主材，将辅材合并到主材
    _merge_low_ratio_aux_to_main(result, craft)
    result.cost_unit_price = _component_total(result.as_components())
    result.field_confidence = {k: line_conf for k in ("material_main", "material_aux", "labor", "machinery")}
    result.confidence = line_conf
    strong_name = name_score >= weak_name_min
    # 主阈值：auto_min (如0.76)；弱匹配阈值：auto_min - 0.02 (如0.74)
    weak_auto_threshold = max(auto_min - 0.02, 0.70)
    auto_ok = line_conf >= auto_min or (
        strong_name and line_conf >= weak_min and _components_usable(comps)
    )
    # 弱匹配：如果line_conf >= weak_auto_threshold，也允许自动填充（标记为line_match_weak）
    # material-only（仅主材无人工）不自动填，让后续层（市场参考等）接管
    weak_auto_ok = (
        not auto_ok
        and line_conf >= weak_auto_threshold
        and _components_usable(comps)
        and not _is_material_only(comps)
    )
    result.source = "line_match" if auto_ok else "line_match_weak"
    result.auto_fill_ok = allow_auto and (auto_ok or weak_auto_ok)
    if weak_auto_ok:
        result.notes.append(f"[弱匹配自动填充] 置信度{line_conf:.0%}≥{weak_auto_threshold:.0%}")
    result.notes.append(note)
    result.warnings = _validate_expectations(craft, result.as_components(), role)
    return _finalize_for_output(result, name, feature)


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

    # 分来源auto_fill阈值配置（核心OK=100%的来源适度放宽）
    source_thresholds = judge_cfg.get("source_specific_auto_thresholds", {})

    def _get_auto_threshold(source: str) -> float:
        """获取指定来源的auto_fill阈值，若无配置则使用全局auto_min"""
        return source_thresholds.get(source, auto_min)

    # line_match来源特定阈值
    line_match_threshold = _get_auto_threshold("line_match")

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

    # 已验证高准确率来源，置信度足够时绕过特征限制
    # market_reference 移至半信任：特征充足时 auto_fill，特征不足时回退
    trusted_sources = {"line_match", "mep_install_profile",
                       "special_line_price", "project_material_code", "metal_trim_profile",
                       "decorative_diffuser_length"}
    semi_trusted_sources = {"market_reference"}

    def _auto(ok: bool, source: str = "") -> bool:
        if ok and block_auto and source in trusted_sources:
            src_threshold = _get_auto_threshold(source)
            if source == "line_match" and ok:
                return True
            if source in trusted_sources and ok:
                return True
        # 半信任来源：仅当特征充足(feat_ok)时才允许 auto_fill，否则回退到人工确认
        if ok and block_auto and source in semi_trusted_sources and feat_ok:
            return True
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

    def _done(r: ComponentJudgment) -> ComponentJudgment:
        return _finalize_for_output(r, name, feature, unit)

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
                return _done(result)

    # --- 层 0a2：多主材组合柜体/前台（整项历史价）---
    from src.pricing.custom_furniture import lookup_composite_furniture_line

    comp_furn, comp_furn_note = lookup_composite_furniture_line(
        name, feature, unit, repo, ctx
    )
    if comp_furn and _components_usable(comp_furn):
        result.material_main = float(comp_furn.get("material_main") or 0)
        result.material_aux = float(comp_furn.get("material_aux") or 0)
        result.labor = float(comp_furn.get("labor") or 0)
        result.machinery = float(comp_furn.get("machinery") or 0)
        result.material_loss_rate = float(comp_furn.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        result.confidence = 0.88
        result.field_confidence = {k: 0.88 for k in ("material_main", "material_aux", "labor", "machinery")}
        result.source = "composite_furniture_line"
        result.notes.append(comp_furn_note)
        result.auto_fill_ok = _auto(result.confidence >= auto_min)
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

    # --- 层 0b：定制门整项（㎡）优先于 WD/MT 表价误套 ---
    door_whole, door_whole_note = lookup_door_whole_line_price(
        name, feature, unit, engine, repo, ctx
    )
    if door_whole and _components_usable(door_whole):
        result.material_main = float(door_whole.get("material_main") or 0)
        result.material_aux = float(door_whole.get("material_aux") or 0)
        result.labor = float(door_whole.get("labor") or 0)
        result.machinery = float(door_whole.get("machinery") or 0)
        result.material_loss_rate = float(door_whole.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        result.confidence = 0.86
        result.field_confidence = {k: 0.86 for k in ("material_main", "material_aux", "labor", "machinery")}
        result.source = "door_whole_line"
        result.notes.append(door_whole_note)
        result.auto_fill_ok = _auto(result.confidence >= auto_min)
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

    # --- 层 0c：塑料管按 DN 拆价（优先于弱整项误套）---
    from src.pricing.plastic_pipe import lookup_plastic_pipe_components

    pipe_comps, pipe_note = lookup_plastic_pipe_components(name, feature, unit)
    if pipe_comps and _components_usable(pipe_comps):
        result.material_main = float(pipe_comps.get("material_main") or 0)
        result.material_aux = float(pipe_comps.get("material_aux") or 0)
        result.labor = float(pipe_comps.get("labor") or 0)
        result.machinery = float(pipe_comps.get("machinery") or 0)
        result.material_loss_rate = float(pipe_comps.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        # 口径A（含管件）/HDPE/静音/UPVC冷凝水表为逐档校准样本；口径B纯管材表经校准
        # 2026-08-18 重构后按"含管道配件"特征区分两套口径，恢复自动填
        result.confidence = 0.85
        result.field_confidence = {k: 0.85 for k in ("material_main", "material_aux", "labor", "machinery")}
        result.source = "plastic_pipe_dn"
        result.notes.append(pipe_note)
        pipe_auto_threshold = max(_get_auto_threshold("line_match") + 0.02, 0.82)
        result.auto_fill_ok = _auto(result.confidence >= pipe_auto_threshold)
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

    # --- 层 0d：深海 CL 灯槽/边槽天花涂料（含基层，优先于饰面工序）---
    from src.pricing.material_process_price import lookup_ceiling_cl_paint

    cl_comps, cl_note = lookup_ceiling_cl_paint(name, feature, unit)
    if cl_comps and _components_usable(cl_comps):
        result.material_main = float(cl_comps.get("material_main") or 0)
        result.material_aux = float(cl_comps.get("material_aux") or 0)
        result.labor = float(cl_comps.get("labor") or 0)
        result.machinery = float(cl_comps.get("machinery") or 0)
        result.material_loss_rate = float(cl_comps.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        result.confidence = 0.88
        result.field_confidence = {k: 0.88 for k in ("material_main", "material_aux", "labor", "machinery")}
        result.source = "ceiling_cl_paint"
        result.notes.append(cl_note)
        result.auto_fill_ok = _auto(result.confidence >= auto_min)
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

    # --- 层 0e：装饰条形风口按规格长度计延长米价（深海定稿）---
    from src.pricing.decorative_diffuser import lookup_decorative_diffuser_components

    vent_comps, vent_note = lookup_decorative_diffuser_components(name, feature, unit)
    if vent_comps and _components_usable(vent_comps):
        result.material_main = float(vent_comps.get("material_main") or 0)
        result.material_aux = float(vent_comps.get("material_aux") or 0)
        result.labor = float(vent_comps.get("labor") or 0)
        result.machinery = float(vent_comps.get("machinery") or 0)
        result.material_loss_rate = float(vent_comps.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        result.confidence = 0.9
        result.field_confidence = {k: 0.9 for k in ("material_main", "material_aux", "labor", "machinery")}
        result.source = "decorative_diffuser_length"
        result.notes.append(vent_note)
        # decorative_diffuser_length核心OK=100%，使用来源特定阈值0.72
        vent_threshold = _get_auto_threshold("decorative_diffuser_length")
        result.auto_fill_ok = _auto(result.confidence >= vent_threshold, "decorative_diffuser_length")
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

    # --- 层 0f：定稿特殊清单（开孔/护角弧形/洗漱台，优先于主材表误套）---
    from src.pricing.special_line_price import lookup_special_line_components

    from src.pricing.residential_finish_price import lookup_residential_finish_components

    res_comps, res_note = lookup_residential_finish_components(
        name, feature, unit, city=(ctx.city if ctx else "")
    )
    if res_comps and (
        _components_usable(res_comps) or "合入他项" in (res_note or "")
    ):
        result.material_main = float(res_comps.get("material_main") or 0)
        result.material_aux = float(res_comps.get("material_aux") or 0)
        result.labor = float(res_comps.get("labor") or 0)
        result.machinery = float(res_comps.get("machinery") or 0)
        result.material_loss_rate = float(res_comps.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        result.confidence = 0.84
        result.field_confidence = {k: 0.84 for k in ("material_main", "material_aux", "labor", "machinery")}
        result.source = "residential_finish_profile"
        result.notes.append(res_note)
        result.auto_fill_ok = _auto(result.confidence >= auto_min)
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

    special_comps, special_note = lookup_special_line_components(name, feature, unit)
    if special_comps and _components_usable(special_comps):
        result.material_main = float(special_comps.get("material_main") or 0)
        result.material_aux = float(special_comps.get("material_aux") or 0)
        result.labor = float(special_comps.get("labor") or 0)
        result.machinery = float(special_comps.get("machinery") or 0)
        result.material_loss_rate = float(special_comps.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        special_final = "定稿" in (special_note or "")
        result.confidence = 0.9 if special_final else 0.76
        result.field_confidence = {
            k: result.confidence for k in ("material_main", "material_aux", "labor", "machinery")
        }
        result.source = "special_line_price"
        result.notes.append(special_note)
        # special_line_price核心OK=100%，使用来源特定阈值0.75
        special_threshold = _get_auto_threshold("special_line_price")
        result.auto_fill_ok = _auto(result.confidence >= special_threshold, "special_line_price")
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

    # --- 层 0f3：VRF/洁具/广播（会所安装 sheet 常见项）---
    from src.pricing.mep_install_price import lookup_mep_install_components

    mep_comps, mep_note = lookup_mep_install_components(name, feature, unit)
    if mep_comps and _components_usable(mep_comps):
        result.material_main = float(mep_comps.get("material_main") or 0)
        result.material_aux = float(mep_comps.get("material_aux") or 0)
        result.labor = float(mep_comps.get("labor") or 0)
        result.machinery = float(mep_comps.get("machinery") or 0)
        result.material_loss_rate = float(mep_comps.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        # 各MEP类别按实际审计准确率分级信任
        mep_trusted = any(
            tag in (mep_note or "")
            for tag in ("[冷媒铜管]", "[风管软接头]", "[电气]开关", "[电气]插座",
                        "[洁具]台盆", "[洁具]水槽", "[洁具]拖把池")
        )
        if "[断路器]" in (mep_note or ""):
            mep_trusted = "分励" in (mep_note or "") or not re.search(
                r"NM1|塑壳|NXMLE|1000A|400A|250A", name, re.I
            )
        result.confidence = 0.84 if mep_trusted else 0.72
        result.field_confidence = {
            k: result.confidence for k in ("material_main", "material_aux", "labor", "machinery")
        }
        result.source = "mep_install_profile"
        result.notes.append(mep_note)
        # mep_install_profile核心OK=100%，使用来源特定阈值0.72
        mep_threshold = _get_auto_threshold("mep_install_profile")
        result.auto_fill_ok = _auto(result.confidence >= mep_threshold, "mep_install_profile")
        
        # 断路器后备：若mep_install_profile不能auto_fill（通常因特征短被block_auto），
        # 尝试market_reference，若匹配成功则直接允许auto_fill
        if not result.auto_fill_ok and "[断路器]" in (mep_note or ""):
            mkt_city = ctx.city if ctx else ""
            mkt_tier = ctx.price_tier if ctx else "mid"
            market = lookup_market_reference(name, feature, unit, city=mkt_city, tier=mkt_tier)
            if market and market.confidence >= _get_auto_threshold("market_reference"):
                result.material_main = float(market.material_main or 0)
                result.material_aux = float(market.material_aux or 0)
                result.labor = float(market.labor or 0)
                result.machinery = float(market.machinery or 0)
                result.material_loss_rate = float(getattr(market, "loss_rate", 0) or 0)
                result.cost_unit_price = _component_total(result.as_components())
                result.field_confidence = {k: market.confidence for k in ("material_main", "material_aux", "labor", "machinery")}
                result.confidence = market.confidence
                result.source = "market_reference"
                result.notes.append(f"断路器后备规则：{market.note}")
                # 断路器后备：仍走阈值判断，防止错误市场价自动填入
                result.auto_fill_ok = _auto(market.confidence >= _get_auto_threshold("market_reference"), "market_reference")
        
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

    # --- 层 0f4：截面可解析的电力电缆（避免跨规格历史误套）---
    from src.pricing.mep_install_price import lookup_power_cable_components

    cable_early, cable_early_note = lookup_power_cable_components(name, feature, unit)
    if cable_early and _components_usable(cable_early):
        result.material_main = float(cable_early.get("material_main") or 0)
        result.material_aux = float(cable_early.get("material_aux") or 0)
        result.labor = float(cable_early.get("labor") or 0)
        result.machinery = float(cable_early.get("machinery") or 0)
        result.material_loss_rate = float(cable_early.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        result.source = "mep_install_profile"
        result.notes.append(cable_early_note)
        
        # 电缆截面解析明确时，允许auto_fill
        cable_threshold = _get_auto_threshold("mep_install_profile")
        # 截面解析成功即采信解析价（原"市场参考校准"已删除：市场规则多为无规格分档的
        # 小截面敷设价，如 electrical_power_cable 65元/m 对应 4×10 级，会把 4×95+1×50
        # 的 301 元/m 覆盖成 65 元/m，福永实证 -79%）
        result.confidence = 0.84
        result.field_confidence = {
            k: 0.84 for k in ("material_main", "material_aux", "labor", "machinery")
        }
        # 电缆截面解析明确，走阈值判断
        result.auto_fill_ok = _auto(result.confidence >= cable_threshold, "mep_install_profile")

        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

    # --- 层 0f2：照明物料代号（Mr15n/D13f/Wi12 等，名称含代号即可）---
    from src.pricing.lighting_fixture_price import lookup_lighting_fixture_components

    light_comps, light_note = lookup_lighting_fixture_components(
        name, feature, unit, city=(ctx.city if ctx else "")
    )
    if light_comps and _components_usable(light_comps):
        result.material_main = float(light_comps.get("material_main") or 0)
        result.material_aux = float(light_comps.get("material_aux") or 0)
        result.labor = float(light_comps.get("labor") or 0)
        result.machinery = float(light_comps.get("machinery") or 0)
        result.material_loss_rate = float(light_comps.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        result.confidence = 0.86
        result.field_confidence = {k: 0.86 for k in ("material_main", "material_aux", "labor", "machinery")}
        result.source = "lighting_fixture_code"
        result.notes.append(light_note)
        result.auto_fill_ok = _auto(result.confidence >= auto_min)
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

    # --- 层 0：项目主材编号表（名称/特征含 PT-01、ST-04 → 售楼处主材料价）---
    from src.knowledge.project_materials import extract_material_codes
    from src.pricing.project_material_lookup import (
        lookup_project_material_components,
        lookup_named_material_main,
    )

    # 无编号主材表（重黔站房）：仅绑定本项目时按名称取主材价，不拆人工辅材
    if ctx and ctx.project_materials_ref and not extract_material_codes(name, feature):
        named_comps, named_note = lookup_named_material_main(
            name, feature, unit, ctx=ctx, db_path=repo.db_path
        )
        if named_comps and _components_usable(named_comps):
            # 表价只补主材。已有同城历史人工/辅材则留下，禁止把综合单价主材清成 0。
            hist = None
            if ctx:
                from src.match.engine import best_match

                conn = repo.conn()
                try:
                    pool = engine._load_pool(conn)
                finally:
                    conn.close()
                cand, _level = best_match(
                    name, feature, unit, pool, th=engine.thresholds, mode=engine.mode
                )
                same_name = bool(
                    cand
                    and (
                        cand.name_score >= 0.85
                        or normalize_name(cand.name_norm) == normalize_name(name)
                    )
                )
                if same_name:
                    hist = _same_name_hist(repo, name, unit, ctx) or (
                        repo.get_line_fact(cand.standard_item_id, ctx)[0]
                    )
            if hist and (
                float(hist.get("labor") or 0) > 0 or float(hist.get("material_aux") or 0) > 0
            ):
                result.material_main = float(named_comps.get("material_main") or 0)
                result.material_loss_rate = float(named_comps.get("material_loss_rate") or 0)
                result.material_aux = float(hist.get("material_aux") or 0)
                result.labor = float(hist.get("labor") or 0)
                result.machinery = float(hist.get("machinery") or 0)
                result.cost_unit_price = _component_total(result.as_components())
                result.confidence = 0.9
                result.field_confidence = {
                    "material_main": 0.92,
                    "material_aux": 0.85,
                    "labor": 0.85,
                    "machinery": 0.8,
                }
                result.source = "project_material_code"
                result.notes.append(named_note)
                result.notes.append("主材取项目表价，人工/辅材沿用同城历史")
                result.auto_fill_ok = _auto(result.confidence >= auto_min)
                result.warnings = _validate_expectations(craft, result.as_components(), role)
                return _done(result)

    if extract_material_codes(name, feature):
        # 特殊项目：石材干挂、石材暗门、岩板暗门、除尘地毯、人造石等是综合单价（含安装）
        # 不是单纯材料价，应跳过project_material_code，走market_reference
        text = normalize_name(f"{name}\n{feature}")
        is_special_project = re.search(r"石材干挂|石材暗门|岩板暗门|除尘地毯|人造石|米白色大理石|干挂.*石材|石材.*干挂", text)
        if not is_special_project:
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
                return _done(result)

    # --- 层 0m：明确展开面的金属线条优先于历史弱整项 ---
    trim_comps, trim_note = lookup_metal_trim_price(name, feature, unit, repo, ctx)
    if trim_comps and _components_usable(trim_comps):
        result.material_main = float(trim_comps.get("material_main") or 0)
        result.material_aux = float(trim_comps.get("material_aux") or 0)
        result.labor = float(trim_comps.get("labor") or 0)
        result.machinery = float(trim_comps.get("machinery") or 0)
        result.material_loss_rate = float(trim_comps.get("material_loss_rate") or 0)
        result.cost_unit_price = _component_total(result.as_components())
        result.confidence = 0.78
        result.field_confidence = {
            k: 0.78 for k in ("material_main", "material_aux", "labor", "machinery")
        }
        result.source = "metal_trim_profile"
        result.notes.append(trim_note)
        # metal_trim_profile核心OK=100%，使用来源特定阈值0.77
        result.auto_fill_ok = _auto(result.confidence >= _get_auto_threshold("metal_trim_profile"), "metal_trim_profile")
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

    def _extract_diameter(text_str):
        patterns = [
            r"(?:JDG|KBG)(\d{2,3})",
            r"DN(\d{2,3})",
            r"(?:SC)(\d{2,3})",
            r"[φΦ](\d{2,3})",
        ]
        for pat in patterns:
            m = re.search(pat, text_str, re.I)
            if m:
                return int(m.group(1))
        return None

    def _extract_cable_spec(text_str):
        cable_pat = (
            r"(?:WDZ[A-Z0-9-]*|ZR|NH|KVV|YJLV|YJV)?-?"
            r"(?:YJLV|YJV)[A-Z0-9-]*\s*-?\s*"
            r"((?:\d+\s*[x×*]\s*\d+(?:\.\d+)?)(?:\s*\+\s*\d+\s*[x×*]\s*\d+(?:\.\d+)?)*)"
        )
        m = re.search(cable_pat, text_str, re.I)
        if m:
            spec = re.sub(r"\s+", "", m.group(1)).replace("×", "*").replace("x", "*").replace("X", "*")
            return spec
        m2 = re.search(r"((?:\d+\s*[x×*]\s*\d+(?:\.\d+)?)(?:\s*\+\s*\d+\s*[x×*]\s*\d+(?:\.\d+)?)*)", text_str, re.I)
        if m2:
            return re.sub(r"\s+", "", m2.group(1)).replace("×", "*").replace("x", "*").replace("X", "*")
        return None

    # --- 层 0：专项规则（优先于历史匹配）---
    text = normalize_name(f"{name}\n{feature}")
    is_jdg_conduit = re.search(r"JDG|KBG|配管", text)
    # 项目编号物料（MT-、WD-、CT-、PT-等）优先走project_material_code，排除层0拦截
    has_project_code = re.search(r"(?:MT|WD|CT|PT|ST|MB)-?\d+", text)
    is_fire_item = re.search(r"烟感|探测器|消防广播|消火栓箱|消火栓|BTTZ|消防联动|消防电缆|消防箱暗门|热镀锌钢管|喷淋头|手动报警按钮|消防按钮|消防主机|排烟风机|防火阀|排烟阀|消防水泵|消防泵|消防水箱|启泵按钮|短路隔离|水灭火|执行机构|压力表|消防端子箱|消防电话|功率放大器|增压稳压|组合式消火栓|试验消火栓|消防管道|消火栓按钮", text)
    is_construction_item = re.search(r"混凝土地面开挖|隔油池|U形槽|玻璃栏板|防爆膜|墙面抹灰|水泥|洗车房地垫|焊条|白玉兰大理石|化粪池|承重井盖|钢井盖|铁艺大门|伸缩门|防撞杆|土方开挖|土方回填|土方清运|垃圾清运|大门新做", text)
    is_lighting_item = re.search(r"格栅灯|普通灯具|吸顶灯|声控|筒灯|吊灯|灯带|条形灯|线型灯|灯具安装", text)
    is_fire_extinguisher = re.search(r"干粉灭火器|灭火器", text)
    is_special_item = re.search(r"空调设计费|暖气片安装|电力电缆头|电缆终端头|胶泥|虎皮兰|条形灯|线型灯|YJV|YJLV|电缆|全玻幕墙|电动卷帘|NXB|NB6|NXM|NA1|断路器|蝶阀|闸阀|止回阀|截止阀|水表|风机盘管|风幕机|空气幕|分体空调|多联式空调室内机|四面出风|加气混凝土|铝塑板|铝板弧形|沥青混凝土|结构检测|室外坡道|镜面柜|岩板包边|瓷砖包边|双面双层石膏板|无框玻璃门|地弹簧玻璃门|铁皮保护层|橡胶软接|地面划线|设备间暗门|入户大堂门|配电箱元器件|NXU-Ⅱ|单联双控开关|金属框玻璃窗|拆除钢楼梯|电容互感器|LMZJ1|应急电池|防水无纺布|JS防水层|卫生间包管|落地式配电箱|PDI灯光房|WD-04木饰面|WD-04|双扇玻璃自动门|除尘地毯|风量调节阀|NXMLE|不锈钢地漏|混凝土构件拆除|空调机组室外机|湿式报警阀|报警阀组|雨淋阀|预作用阀|水流指示器|不锈钢防滑板|不锈钢槽钢|不锈钢方管|不锈钢方通|不锈钢挂架|不锈钢围栏|不锈钢平台|304不锈钢|设备移位|设备恢复安装|管道破损修复|水处理内部修复|焊接|措施费|加药口|轴流风机|排气扇|排风机|多联机|室内机安装|风盘|软连接|软管|制冷剂|空调调试|检修门|水吧柜|数据点位|扬声器|接地装置|电动伸缩门|风量调节阀（VD）|防火阀|排烟防火阀|执行机构|烟感探测器|火灾报警按钮|模块|消火栓启泵|消火栓按钮|压力表|短路隔离器|化粪池|承重井盖|钢井盖|箭头|斑马线|划线及标识|防撞杆|土方清运|垃圾清运|伸缩门|铁艺大门|大门新做|穿楼板|屋面防水|挡水|水泥基座|发泡胶|塞口|反支撑|磁吸灯|洗墙灯|软灯条|工艺吊灯|水磨石砖|洞洞板|软木板|苔藓墙|白板墙|防滑条|窗台板|吸音棉|吸音板|检修口|推拉门|入户门|地柜|镜柜|更衣柜|过梁|钢梯|圈梁|构造柱|混凝土坡道|卷材防水|洗手台|卫生间镜子|成品隔断|钢制防火门|百叶窗|伸缩缝|瓦楞板|夹芯板|铝板一体板|散水台|仿水磨石地胶|钢丝网|岩板|马桶|污水提升泵|电能表|金属篦子|道牙|护角|防撞条|不锈钢窗套|竹胶板|高密度聚乙烯|钢塑围栏|模板（综合）|现浇构件钢筋|电梯|智能水电表|一体板|幕墙窗帘盒", text)
    
    # 特殊情况：WD-04木饰面等项目编号但实际是市场参考价的项目
    # 数据库中没有WD-04，但market_reference中有wall_wood_veneer_wd04规则
    # 石材干挂、石材暗门、岩板暗门等是综合单价（含安装），不是单纯材料价
    is_special_project_code = re.search(r"木饰面|石材干挂|石材暗门|岩板暗门|除尘地毯|人造石|门槛石|过门石|石材门槛", text) and has_project_code
    
    # --- 层 0f4：截面可解析的电力电缆（避免跨规格历史误套）---
    # 优先于is_special_item的market_reference，因为电缆有专门的定价逻辑
    is_power_cable = bool(re.search(r"电缆|YJV|YJLV", text, re.I))
    if is_power_cable and not is_jdg_conduit:
        from src.pricing.mep_install_price import lookup_power_cable_components

        cable_comps, cable_note = lookup_power_cable_components(name, feature, unit)
        if cable_comps and _components_usable(cable_comps):
            result.material_main = float(cable_comps.get("material_main") or 0)
            result.material_aux = float(cable_comps.get("material_aux") or 0)
            result.labor = float(cable_comps.get("labor") or 0)
            result.machinery = float(cable_comps.get("machinery") or 0)
            result.material_loss_rate = float(cable_comps.get("material_loss_rate") or 0)
            result.cost_unit_price = _component_total(result.as_components())
            result.confidence = 0.84
            result.field_confidence = {
                k: 0.84 for k in ("material_main", "material_aux", "labor", "machinery")
            }
            result.source = "mep_install_profile"
            result.notes.append(cable_note)
            cable_threshold = _get_auto_threshold("mep_install_profile")
            result.auto_fill_ok = _auto(result.confidence >= cable_threshold, "mep_install_profile")
            result.warnings = _validate_expectations(craft, result.as_components(), role)
            return _done(result)

    if (is_fire_item or is_construction_item or is_lighting_item or is_fire_extinguisher or is_special_item or is_special_project_code) and not is_jdg_conduit and (not has_project_code or is_special_project_code):
        mkt_city = ctx.city if ctx else ""
        mkt_tier = ctx.price_tier if ctx else "mid"
        market = lookup_market_reference(name, feature, unit, city=mkt_city, tier=mkt_tier)
        if market:
            result.material_main = float(market.material_main or 0)
            result.material_aux = float(market.material_aux or 0)
            result.labor = float(market.labor or 0)
            result.machinery = float(market.machinery or 0)
            result.material_loss_rate = float(getattr(market, "loss_rate", 0) or 0)
            # 主材利旧：主材费为0（材料回收利用）
            _text = normalize_name(f"{name}\n{feature}")
            if "主材利旧" in _text or "利旧" in _text:
                result.material_main = 0.0
            result.cost_unit_price = _component_total(result.as_components())
            fc = {k: market.confidence for k in ("material_main", "material_aux", "labor", "machinery")}
            result.field_confidence = fc
            result.confidence = market.confidence
            result.source = "market_reference"
            result.notes.append(f"专项规则：{market.note}")
            # market_reference核心OK=100%，直接允许auto_fill（绕过block_auto）
            result.auto_fill_ok = result.confidence >= _get_auto_threshold("market_reference")
            result.warnings = _validate_expectations(craft, result.as_components(), role)
            return _done(result)

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
        text = normalize_name(f"{name}\n{feature}")
        is_conduit = re.search(r"配管|JDG|KBG|电线管|镀锌钢管|SC钢管|焊接钢管", text)
        is_cable = re.search(r"电缆|YJV|YJLV", text, re.I)
        skip_strong_match = False
        if is_conduit and line_conf >= auto_min:
            query_dia = _extract_diameter(text)
            cand_name = cands[0].get("name_norm", "") or cands[0].get("name", "")
            cand_dia = _extract_diameter(cand_name)
            if query_dia is not None and cand_dia is not None and query_dia != cand_dia:
                skip_strong_match = True
        if is_cable and line_conf >= auto_min:
            query_spec = _extract_cable_spec(text)
            cand_name = cands[0].get("name_norm", "") or cands[0].get("name", "")
            cand_spec = _extract_cable_spec(cand_name)
            if query_spec is not None and cand_spec is not None and query_spec != cand_spec:
                skip_strong_match = True

        if line_conf >= auto_min and not skip_strong_match:
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
                _merge_low_ratio_aux_to_main(result, craft)
                result.cost_unit_price = _component_total(result.as_components())
                fc = {k: line_conf for k in ("material_main", "material_aux", "labor", "machinery")}
                result.field_confidence = fc
                result.confidence = line_conf
                result.source = "line_match"
                result.notes.append(note)
                result.auto_fill_ok = _auto(True)
                result.warnings = _validate_expectations(craft, result.as_components(), role)
                return _done(result)
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
        # metal_trim_profile核心OK=100%，使用来源特定阈值0.77
        result.auto_fill_ok = _auto(result.confidence >= _get_auto_threshold("metal_trim_profile"), "metal_trim_profile")
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

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
        # custom_door_profile核心OK=100%，允许自动填充
        result.auto_fill_ok = _auto(result.confidence >= _get_auto_threshold("line_match_weak"), "custom_door_profile")
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

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
        return _done(result)

    # --- 层 1b：弱整项（≥75% 或名称强命中）取历史全量人材机 ---
    mkt_city = ctx.city if ctx else ""
    mkt_tier = ctx.price_tier if ctx else "mid"
    market = lookup_market_reference(name, feature, unit, city=mkt_city, tier=mkt_tier)

    weak_feature_min = float(cfg.get("reference_line", {}).get("weak_feature_min", 0.58))
    if cands:
        id_reject = _weak_candidate_rejected(
            name, feature, cands[0], feat_min=weak_feature_min
        )
        weak_comps, weak_note = (None, "")
        if not id_reject:
            weak_comps, weak_note = _fetch_line_components_from_candidate(
                cands[0], repo, ctx, cfg,
                unit=unit, net_divisor=net_divisor, name=name, feature=feature, craft=craft,
            )
        name_ok = cands[0].get("name_score", 0) >= weak_name_min
        feat_score = float(cands[0].get("feature_score") or 0)
        feat_ok = feat_score >= weak_feature_min or not (cands[0].get("feature") or "").strip()
        
        text = normalize_name(f"{name}\n{feature}")
        is_conduit = re.search(r"配管|JDG|KBG|电线管|镀锌钢管|SC钢管|焊接钢管", text)
        is_cable = re.search(r"电缆|YJV|YJLV", text, re.I)
        skip_weak_match = False
        if is_conduit and weak_comps:
            query_dia = _extract_diameter(text)
            cand_name = cands[0].get("name_norm", "") or cands[0].get("name", "")
            cand_dia = _extract_diameter(cand_name)
            if query_dia is not None and cand_dia is not None and query_dia != cand_dia:
                skip_weak_match = True
        if is_cable and weak_comps:
            query_spec = _extract_cable_spec(text)
            cand_name = cands[0].get("name_norm", "") or cands[0].get("name", "")
            cand_spec = _extract_cable_spec(cand_name)
            if query_spec is not None and cand_spec is not None and query_spec != cand_spec:
                skip_weak_match = True
        
        if weak_comps and (
            line_conf >= weak_min or (name_ok and feat_ok and line_conf >= review_min)
        ) and not skip_weak_match and not _is_material_only(weak_comps):
            prefer_market = bool(
                market and _is_baggy_line_name(name) and feat_score < 0.75
            )
            if not prefer_market:
                return _done(
                    _apply_line_components(
                    result, weak_comps, line_conf, line_match_threshold, weak_note, craft, role,
                    name=name,
                    feature=feature,
                    name_score=cands[0].get("name_score", 0),
                    weak_min=weak_min,
                    weak_name_min=weak_name_min,
                    allow_auto=not block_auto,
                    )
                )
            result.notes.append(f"泛称弱整项让位市场参考：{weak_note}")
        elif id_reject:
            result.notes.append(f"拒绝弱整项：{id_reject}")

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
            return _done(result)

    def _extract_diameter(text_str):
        import re
        patterns = [
            r"(?:JDG|KBG)(\d{2,3})",
            r"DN(\d{2,3})",
            r"(?:SC)(\d{2,3})",
            r"[φΦ](\d{2,3})",
        ]
        for pat in patterns:
            m = re.search(pat, text_str, re.I)
            if m:
                return int(m.group(1))
        return None

    # --- 层 1g：无编号/产品名冲突的历史整项优先于市场参考 ---
    if cands and line_conf >= review_min:
        if not _weak_candidate_rejected(name, feature, cands[0], feat_min=weak_feature_min):
            hist_comps, hist_note = _fetch_line_components_from_candidate(
                cands[0], repo, ctx, cfg,
                unit=unit, net_divisor=net_divisor, name=name, feature=feature, craft=craft,
            )
            # material-only（仅主材无人工/辅材/机械）不作为整项价，让位市场参考等层
            if hist_comps and _components_usable(hist_comps) and not _is_material_only(hist_comps):
                name_sc = float(cands[0].get("name_score") or 0)
                line_is_weak = line_conf < auto_min or not (name_sc >= weak_name_min and line_conf >= weak_min)
                text = normalize_name(f"{name}\n{feature}")
                is_conduit = re.search(r"配管|JDG|KBG|电线管|镀锌钢管|SC钢管|焊接钢管", text)
                is_cable = re.search(r"电缆|YJV|YJLV", text, re.I)
                use_conduit_rule = False
                use_cable_rule = False
                if is_conduit:
                    query_dia = _extract_diameter(text)
                    cand_name = cands[0].get("name_norm", "") or cands[0].get("name", "")
                    cand_dia = _extract_diameter(cand_name)
                    if query_dia is not None and cand_dia is not None and query_dia != cand_dia:
                        use_conduit_rule = True
                    elif line_is_weak:
                        use_conduit_rule = True
                if is_cable:
                    query_spec = _extract_cable_spec(text)
                    cand_name = cands[0].get("name_norm", "") or cands[0].get("name", "")
                    cand_spec = _extract_cable_spec(cand_name)
                    if query_spec is not None and cand_spec is not None and query_spec != cand_spec:
                        use_cable_rule = True
                    elif line_is_weak:
                        use_cable_rule = True
                if use_conduit_rule or use_cable_rule:
                    from src.pricing.mep_install_price import lookup_mep_cable_conduit_fallback
                    fb_comps, fb_note = lookup_mep_cable_conduit_fallback(name, feature, unit)

                    if fb_comps and _components_usable(fb_comps):
                        result.material_main = float(fb_comps.get("material_main") or 0)
                        result.material_aux = float(fb_comps.get("material_aux") or 0)
                        result.labor = float(fb_comps.get("labor") or 0)
                        result.machinery = float(fb_comps.get("machinery") or 0)
                        result.material_loss_rate = float(fb_comps.get("material_loss_rate") or 0)
                        result.cost_unit_price = _component_total(result.as_components())
                        result.confidence = 0.84
                        result.field_confidence = {
                            k: 0.84 for k in ("material_main", "material_aux", "labor", "machinery")
                        }
                        result.source = "mep_install_profile"
                        result.notes.append(fb_note)
                        # 配管/电缆：截面解析明确时允许auto_fill，走阈值判断
                        mep_threshold = _get_auto_threshold("mep_install_profile")
                        result.auto_fill_ok = _auto(result.confidence >= mep_threshold, "mep_install_profile")
                        result.warnings = _validate_expectations(craft, result.as_components(), role)
                        return _done(result)
                return _done(
                    _apply_line_components(
                        result,
                        hist_comps,
                        max(line_conf, review_min),
                        line_match_threshold,
                        (hist_note or "历史整项") + "；优先于市场参考",
                        craft,
                        role,
                        name=name,
                        feature=feature,
                        name_score=name_sc,
                        weak_min=weak_min,
                        weak_name_min=weak_name_min,
                        allow_auto=name_sc >= weak_name_min and line_conf >= weak_min,
                    )
                )

    # --- 层 1h：电缆/配管/零散成品兜底（历史整项不够强时）---
    if line_conf < auto_min:
        from src.pricing.mep_install_price import lookup_mep_cable_conduit_fallback
        from src.pricing.special_line_price import lookup_misc_finish_fallback

        for fetch, src_name, conf_ok in (
            (lookup_mep_cable_conduit_fallback, "mep_install_profile", True),
            (lookup_misc_finish_fallback, "special_line_price", False),
        ):
            fb_comps, fb_note = fetch(name, feature, unit)
            if not (fb_comps and _components_usable(fb_comps)):
                continue
            result.material_main = float(fb_comps.get("material_main") or 0)
            result.material_aux = float(fb_comps.get("material_aux") or 0)
            result.labor = float(fb_comps.get("labor") or 0)
            result.machinery = float(fb_comps.get("machinery") or 0)
            result.material_loss_rate = float(fb_comps.get("material_loss_rate") or 0)
            result.cost_unit_price = _component_total(result.as_components())
            # 扩展auto_fill条件：电力电缆和配管都允许auto_fill，绕过block_auto
            can_auto = conf_ok and ("[电力电缆]" in (fb_note or "") or "配管" in (fb_note or "") or "管道" in (fb_note or ""))
            if can_auto:
                result.confidence = 0.84
            elif src_name == "special_line_price":
                # special_line_price兜底：核心OK=100%，允许auto_fill
                result.confidence = 0.76
            else:
                result.confidence = 0.74
            result.field_confidence = {
                k: result.confidence
                for k in ("material_main", "material_aux", "labor", "machinery")
            }
            result.source = src_name
            result.notes.append(fb_note)
            if src_name == "special_line_price":
                # special_line_price兜底：使用来源特定阈值
                slp_threshold = _get_auto_threshold("special_line_price")
                result.auto_fill_ok = result.confidence >= slp_threshold
            else:
                mep_threshold = _get_auto_threshold("mep_install_profile")
                result.auto_fill_ok = can_auto and result.confidence >= mep_threshold
            result.warnings = _validate_expectations(craft, result.as_components(), role)
            return _done(result)

    # --- 层 2：市场参考价（须名称+特征+单位均达标，禁止无特征平面套价）---
    allow_market = not block_auto or _allow_market_without_feature(name, feature, craft)
    if market and allow_market:
        total = (
            market.material_main
            + market.material_aux
            + market.labor
            + market.machinery
        )
        if (
            not market.preserve_components
            and (_market_use_craft_split(craft) or _labor_dominant_line(name, feature))
        ):
            split_craft = _craft_for_market_split(craft, name, feature)
            alloc = _allocate_by_craft_template(total, split_craft)
            result.material_main = float(alloc.get("material_main") or 0)
            result.material_aux = float(alloc.get("material_aux") or 0)
            result.labor = float(alloc.get("labor") or 0)
            result.machinery = float(alloc.get("machinery") or 0)
            result.notes.append(f"市场合价{total:.2f}按{split_craft.label}份额拆分")
        else:
            result.material_main = market.material_main
            result.material_aux = market.material_aux
            result.labor = market.labor
            result.machinery = market.machinery
        # 主材利旧：主材费为0（材料回收利用）
        _text2 = normalize_name(f"{name}\n{feature}")
        if "主材利旧" in _text2 or "利旧" in _text2:
            result.material_main = 0.0
        result.material_loss_rate = market.material_loss_rate
        result.cost_unit_price = total
        result.field_confidence = {k: market.confidence for k in ("material_main", "material_aux", "labor", "machinery")}
        result.confidence = market.confidence
        result.source = "market_reference"
        scope = ctx.scope_note() if ctx else ""
        result.notes.append(f"[市场参考{scope}] {market.note}（规则:{market.rule_id}）")
        # market_reference核心OK=100%，使用来源特定阈值0.75
        note = market.note or ""
        city_grade = (
            market.rule_id.startswith(("sz_", "zh_"))
            or "定稿" in note
            or "海德" in note
        )
        market_threshold = _get_auto_threshold("market_reference")
        # 放宽city_grade条件：confidence>=0.75即可自动填（核心OK=100%）
        result.auto_fill_ok = _auto(
            market.confidence >= market_threshold,
            "market_reference"
        )
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)

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
        if (n >= min_samples or (n >= 2 and profile_conf >= review_min)) and _profile_sane(
            craft.craft_id, unit, prof_comps
        ):
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
            result.auto_fill_ok = _auto(
                profile_conf >= _get_auto_threshold("craft_profile"), "craft_profile"
            )
            result.warnings = _validate_expectations(craft, result.as_components(), role)
            return _done(result)
        else:
            result.notes.append(
                f"工艺价型样本{n}未通过合理性校验或归类为「装饰综合」，已跳过"
            )

    # --- 层 4：主材价库 + 份额模板 ---
    lookup = MaterialPriceLookup(repo.db_path)
    mat, mnote = lookup.find(name, feature or "", unit, ctx=ctx)
    shares = _share_map(craft.template_share)
    hybrid_conf = 0.0

    # 兜底 craft（装饰综合）被非装饰品类行命中时，装饰湿作业份额严重失真
    # （福永实证：端子箱人工882/垫层人工363，安装/土建行主材占比应80%+）。
    # 按品类词表分流份额；装饰词命中则保持装饰份额不动。
    if craft.craft_id == "generic_finish":
        _text = f"{name} {feature or ''}"
        _deco = ("墙", "地面", "楼面", "天棚", "吊顶", "踢脚", "门", "窗", "柜",
                 "台面", "石材", "瓷砖", "砖", "木地板", "地毯", "墙纸", "涂料",
                 "乳胶漆", "油漆", "饰面", "软包", "硬包", "隔断", "幕墙", "栏杆", "扶手")
        _mep = ("空调", "泵", "阀", "仪表", "灯", "箱", "风机", "盘管", "消毒器",
                "洁具", "水龙头", "配电", "电缆", "桥架", "母线", "开关", "插座",
                "探头", "模块", "广播", "监控", "摄像", "探测器", "模块箱", "端子",
                "通风器", "换气", "热水器")
        _civil = ("土方", "混凝土", "垫层", "基础", "园路", "铺装", "拆除", "砌筑",
                  "抹灰", "钢筋", "模板", "脚手架", "路面", "缘石", "树池", "绿化",
                  "种植", "加固", "植筋", "灌浆", "找平", "防水", "保温", "瓦",
                  "排水板", "检查井", "化粪池", "水池")
        if any(k in _text for k in _mep) and not any(k in _text for k in _deco):
            shares = {"material_main": 0.85, "material_aux": 0.05,
                      "labor": 0.08, "machinery": 0.02}
            craft = CraftMatch(**{**craft.__dict__, "label": "安装综合(分流)"})
        elif any(k in _text for k in _civil) and not any(k in _text for k in _deco):
            shares = {"material_main": 0.55, "material_aux": 0.15,
                      "labor": 0.22, "machinery": 0.08}
            craft = CraftMatch(**{**craft.__dict__, "label": "土建综合(分流)"})

    unit_n = normalize_unit(unit)
    bare_bulk = unit_n in ("吨", "t", "kg", "千克") or re.fullmatch(
        r"水泥|砂|石子|钢筋|混凝土|砂浆|胶水|腻子粉",
        normalize_name(name) or "",
    )
    if mat and mat.get("material_main", 0) > 0:
        if craft.craft_id == "stone_crystallization":
            result.notes.append("石材晶面/结晶项跳过主材价库+铺贴模板")
        elif bare_bulk:
            # 散装材料只给主材价，不做装饰份额推算
            result.material_main = float(mat["material_main"])
            result.material_loss_rate = float(mat.get("material_loss_rate") or 0)
            result.cost_unit_price = result.material_main
            result.confidence = 0.7
            result.field_confidence = {"material_main": 0.7}
            result.source = "material_bulk"
            result.notes.append(mnote)
            result.notes.append("散装材料仅主材价")
            result.auto_fill_ok = _auto(False)
            return _done(result)
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
                result.auto_fill_ok = _auto(
                    result.confidence >= _get_auto_threshold("material_plus_template"),
                    "material_plus_template",
                )
                result.warnings = _validate_expectations(craft, result.as_components(), role)
                return _done(result)

    # --- 层 4b：定额匹配（特征描述驱动定价）---
    quota_mgr = QuotaManager(repo)
    matcher = FeatureToQuotaMatcher(quota_mgr)
    
    # 人工/机械单价：城市×工种 从 labor_rates.json 读取（None 走配置默认），档位缩放
    tier_ratio = 1.0
    if ctx and ctx.price_tier == "high":
        tier_ratio = 1.15
    elif ctx and ctx.price_tier == "low":
        tier_ratio = 0.85

    # 加载深圳造价信息作为材料价格库
    material_prices = quota_mgr.load_price_info()

    feature_result = matcher.calculate_from_feature(
        name,
        feature or "",
        unit,
        labor_price=quota_mgr._labor_rates(ctx.city if ctx else "", "").get("labor_unit_price") * tier_ratio
        if ctx else None,
        mach_price=quota_mgr._labor_rates(ctx.city if ctx else "", "").get("machinery_unit_price") * tier_ratio
        if ctx else None,
        material_prices=material_prices,
        city=ctx.city if ctx else "",
    )
    
    if feature_result:
        quota_cost, quota_info = feature_result
        total = sum(quota_cost.values())
        if total > 0:
            match_score = quota_info.get("match_score", 0)

            min_price, max_price = 10, 5000
            unit_norm = (unit or "").lower()
            if unit_norm in ("m", "米"):
                min_price, max_price = 5, 500
            elif unit_norm in ("个", "套", "副"):
                min_price, max_price = 5, 10000
            elif "㎡" in unit_norm or "m2" in unit_norm:
                min_price, max_price = 5, 500
            in_range = not (total < min_price or total > max_price)

            # 2026-10-20 解锁：四册真定额已入库（4057子目：OCR勾稽+期刊价映射+
            # 丢点区间修复+行级一致性修复），样例闸门 obsolete。高分匹配+价格
            # 合理区间+组件完整 → 正式入价；否则维持建议提示不动 judge 输出。
            if match_score >= 75 and in_range and _components_usable(quota_cost):
                conf = 0.80
                result.material_main = float(quota_cost.get("material_main") or 0)
                result.material_aux = float(quota_cost.get("material_aux") or 0)
                result.labor = float(quota_cost.get("labor") or 0)
                result.machinery = float(quota_cost.get("machinery") or 0)
                result.material_loss_rate = 0.0  # 定额消耗量已含施工损耗
                result.cost_unit_price = _component_total(result.as_components())
                result.field_confidence = {
                    k: conf for k in ("material_main", "material_aux", "labor", "machinery")
                }
                result.confidence = conf
                result.source = "quota_feature"
                result.quota_hint = (
                    f"[定额入价] {quota_info.get('quota_code', '')}"
                    f"「{quota_info.get('name', '')}」匹配{match_score:.0f}%"
                )
                result.notes.append(
                    f"[定额入价] {quota_info.get('quota_code', '')}"
                    f"「{quota_info.get('name', '')}」匹配{match_score:.0f}% "
                    f"{total:.2f}元/{quota_info.get('unit') or unit}"
                    f"（期刊价映射+基期价兜底，消耗量含损耗）"
                )
                result.auto_fill_ok = _auto(conf >= _get_auto_threshold("quota_feature"), "quota_feature")
                result.warnings = _validate_expectations(craft, result.as_components(), role)
                return _done(result)

            hint = (
                f"[定额建议·未入价] {quota_info.get('quota_code', '')}"
                f"「{quota_info.get('name', '')}」"
                f"匹配{match_score:.0f}% 参考{total:.2f}元/{quota_info.get('unit') or unit}"
                + (
                    f"（超出{min_price}-{max_price}，仅供核对）"
                    if not in_range
                    else "（匹配分<75，仅供核对）"
                )
            )
            result.quota_hint = hint
            result.notes.append(hint)
            result.warnings.append("定额仅建议，未写入成本")

    # --- 层 5：仅整项弱匹配或模板提示 ---
    layer5_reject = (
        _weak_candidate_rejected(name, feature, cands[0], feat_min=weak_feature_min)
        if cands
        else ""
    )
    if comps and not layer5_reject:
        # material-only（仅主材无人工/辅材/机械）不作为整项价：
        # 若市场参考已有明确规则则优先采用，避免只给主材导致缺人工
        if _is_material_only(comps):
            mkt_now = lookup_market_reference(
                name, feature, unit,
                city=ctx.city if ctx else "",
                tier=ctx.price_tier if ctx else "mid",
            )
            if mkt_now and mkt_now.confidence >= _get_auto_threshold("market_reference"):
                result.material_main = float(mkt_now.material_main or 0)
                result.material_aux = float(mkt_now.material_aux or 0)
                result.labor = float(mkt_now.labor or 0)
                result.machinery = float(mkt_now.machinery or 0)
                result.material_loss_rate = float(getattr(mkt_now, "loss_rate", 0) or 0)
                result.cost_unit_price = _component_total(result.as_components())
                result.confidence = mkt_now.confidence
                result.field_confidence = {
                    k: mkt_now.confidence
                    for k in ("material_main", "material_aux", "labor", "machinery")
                }
                result.source = "market_reference"
                result.notes.append(f"层5 material-only 让位市场参考：{mkt_now.note}")
                result.auto_fill_ok = _auto(True)
                result.warnings = _validate_expectations(craft, result.as_components(), role)
                return _done(result)
        text = normalize_name(f"{name}\n{feature}")
        is_conduit = re.search(r"配管|JDG|KBG|电线管|镀锌钢管|SC钢管|焊接钢管", text)
        if is_conduit and cands:
            query_dia = _extract_diameter(text)
            cand_name = cands[0].get("name_norm", "") or cands[0].get("name", "")
            cand_dia = _extract_diameter(cand_name)
            if query_dia is not None and cand_dia is not None and query_dia != cand_dia:
                from src.pricing.mep_install_price import lookup_mep_cable_conduit_fallback
                fb_comps, fb_note = lookup_mep_cable_conduit_fallback(name, feature, unit)
                if fb_comps and _components_usable(fb_comps):
                    result.material_main = float(fb_comps.get("material_main") or 0)
                    result.material_aux = float(fb_comps.get("material_aux") or 0)
                    result.labor = float(fb_comps.get("labor") or 0)
                    result.machinery = float(fb_comps.get("machinery") or 0)
                    result.material_loss_rate = float(fb_comps.get("material_loss_rate") or 0)
                    result.cost_unit_price = _component_total(result.as_components())
                    result.confidence = 0.84
                    result.field_confidence = {
                        k: 0.84 for k in ("material_main", "material_aux", "labor", "machinery")
                    }
                    result.source = "mep_install_profile"
                    result.notes.append(fb_note)
                    fb_threshold = _get_auto_threshold("mep_install_profile")
                    result.auto_fill_ok = _auto(result.confidence >= fb_threshold, "mep_install_profile")
                    result.warnings = _validate_expectations(craft, result.as_components(), role)
                    return _done(result)
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
        feat_ok = (
            not cands
            or float(cands[0].get("feature_score") or 0) >= weak_feature_min
            or not (cands[0].get("feature") or "").strip()
        )
        # 不再用 review_min 抬自动填：弱特征整项一律人工核对
        auto_ok = line_conf >= auto_min or (
            usable and strong_name and feat_ok and line_conf >= weak_min
        )
        result.source = "line_match" if auto_ok else "line_match_weak"
        result.auto_fill_ok = _auto(auto_ok)
        result.notes.append(note or "弱匹配整项，建议人工核对")
        result.warnings = _validate_expectations(craft, result.as_components(), role)
        return _done(result)
    if layer5_reject:
        result.notes.append(f"层5拒绝弱整项：{layer5_reject}")

    # --- 层 5b：无冲突弱整项兜底（不用过宽的 0.55/0.45）---
    if cands and cands[0].get("name_score", 0) >= 0.72 and not layer5_reject:
        relaxed, rnote = _fetch_line_components_from_candidate(
            cands[0], repo, ctx, cfg,
            unit=unit, net_divisor=net_divisor, name=name, feature=feature, craft=craft,
            name_min=0.72, feat_min=weak_feature_min,
        )
        if relaxed and _components_usable(relaxed):
            text = normalize_name(f"{name}\n{feature}")
            is_conduit = re.search(r"配管|JDG|KBG|电线管|镀锌钢管|SC钢管|焊接钢管", text)
            use_conduit_rule = False
            if is_conduit:
                query_dia = _extract_diameter(text)
                cand_name = cands[0].get("name_norm", "") or cands[0].get("name", "")
                cand_dia = _extract_diameter(cand_name)
                if query_dia is not None and cand_dia is not None and query_dia != cand_dia:
                    use_conduit_rule = True
                else:
                    use_conduit_rule = True
            if use_conduit_rule:
                from src.pricing.mep_install_price import lookup_mep_cable_conduit_fallback
                fb_comps, fb_note = lookup_mep_cable_conduit_fallback(name, feature, unit)
                if fb_comps and _components_usable(fb_comps):
                    result.material_main = float(fb_comps.get("material_main") or 0)
                    result.material_aux = float(fb_comps.get("material_aux") or 0)
                    result.labor = float(fb_comps.get("labor") or 0)
                    result.machinery = float(fb_comps.get("machinery") or 0)
                    result.material_loss_rate = float(fb_comps.get("material_loss_rate") or 0)
                    result.cost_unit_price = _component_total(result.as_components())
                    result.confidence = 0.84
                    result.field_confidence = {
                        k: 0.84 for k in ("material_main", "material_aux", "labor", "machinery")
                    }
                    result.source = "mep_install_profile"
                    result.notes.append(fb_note)
                    fb_threshold2 = _get_auto_threshold("mep_install_profile")
                    result.auto_fill_ok = _auto(result.confidence >= fb_threshold2, "mep_install_profile")
                    result.warnings = _validate_expectations(craft, result.as_components(), role)
                    return _done(result)
            return _done(
                _apply_line_components(
                    result,
                    relaxed,
                    max(line_conf, review_min),
                    line_match_threshold,
                    (rnote or "放宽弱整项") + "；兜底匹配",
                    craft,
                    role,
                    name=name,
                    feature=feature,
                    name_score=float(cands[0].get("name_score") or 0),
                    weak_min=weak_min,
                    weak_name_min=weak_name_min,
                    allow_auto=False,
                )
            )

    # --- 层 6：AI联网询价（兜底定价）---
    # 排除纯数字/编号类项目（如"3.1"、"1.2"等），避免AI误判
    nn = normalize_name(name)
    is_pure_number = bool(re.fullmatch(r"[\d\.\-]+", nn))
    if is_pure_number and len(nn) <= 10:
        result.confidence = 0.35
        result.source = "unresolved"
        result.notes.append(f"项目名「{name}」为纯编号，需人工确认具体内容")
        result.warnings = ["纯编号项目，需人工组价"]
        return result
    
    from src.pricing.ai_price_inquiry import ai_inquire_price
    ai_result = ai_inquire_price(name, feature, unit, ctx.city)
    
    # AI 询价仅在 LLM 真实返回（confidence>=0.6）时才采用
    # 当前 LLM 未接入，所有结果为 rule_based 兜底(max 0.4)，跳过避免污染数据
    ai_conf = ai_result.get('confidence', 0) if ai_result else 0
    ai_src = ai_result.get('source', '') if ai_result else ''
    is_llm_result = ai_conf >= 0.6 and not ai_src.startswith('rule_based')
    if ai_result and is_llm_result:
        result.notes.append(
            f"[AI询价兜底] {ai_result.get('source', 'unknown')}"
        )
        result.material_main = float(ai_result.get("material_main") or 0)
        result.material_aux = float(ai_result.get("material_aux") or 0)
        result.labor = float(ai_result.get("labor") or 0)
        result.machinery = float(ai_result.get("machinery") or 0)
        result.material_loss_rate = 0.02
        result.cost_unit_price = _component_total(result.as_components())
        result.confidence = ai_conf
        result.field_confidence = {
            "material_main": ai_conf * 0.8,
            "material_aux": ai_conf * 0.6,
            "labor": ai_conf * 0.8,
            "machinery": ai_conf * 0.5,
        }
        result.source = "ai_inquiry"
        result.auto_fill_ok = _auto(False, "ai_inquiry")
        result.warnings = ["AI估算价格，建议人工复核"]
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

    # 样例定额只作建议。即使后续来源算出价格，老交付也不把定额价当正式成本。
    if judgment.source == "quota_standard" or (
        judgment.quota_hint and judgment.source in ("", "unresolved", "quota_suggestion")
    ):
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
