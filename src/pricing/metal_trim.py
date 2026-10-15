# -*- coding: utf-8 -*-
"""不锈钢/古铜线条：按展开面(mm)查价库或插值组价。"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.normalize.text import normalize_unit

UNFOLD_RE = re.compile(r"展开面[为：:]?\s*(\d+(?:\.\d+)?)\s*mm", re.I)
# 中山/云湾等清单写法：展开尺寸:27+5+5+10+5+5+27+9=93mm（有合计取合计，无合计取各段之和）
UNFOLD_SUM_RE = re.compile(
    r"展开尺寸[为：:]?\s*([0-9+.\s]+?)\s*(?:[=＝]\s*(\d+(?:\.\d+)?))?\s*mm", re.I
)
HEIGHT_AS_UNFOLD_RE = re.compile(r"[Hh高度]\s*[=：:]?\s*(\d+(?:\.\d+)?)\s*mm", re.I)
# 平板/卡条按可见宽度（无折边展开概念）：优先 "150mm宽"，其次 "宽10mm"
WIDTH_BEFORE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mm\s*宽")
WIDTH_AFTER_RE = re.compile(r"宽\s*(\d+(?:\.\d+)?)\s*mm(?!\s*[厚高深长])")

# 定制制品不走展开面线性价
_SKIP_KEYWORDS = (
    "置物架", "柜", "门套", "门头", "屏风", "服务台", "吧台", "洗手台", "地坪漆",
    "开槽", "包边",
)


def parse_unfold_mm(name: str, feature: str = "") -> Optional[float]:
    text = f"{name} {feature}"
    m = UNFOLD_RE.search(text)
    if m:
        return float(m.group(1))
    sm = UNFOLD_SUM_RE.search(text)
    if sm:
        total = sm.group(2)
        if total:
            return float(total)
        parts = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", sm.group(1))]
        if parts:
            return float(round(sum(parts), 2))
    hm = HEIGHT_AS_UNFOLD_RE.search(text)
    if hm and any(k in text for k in ("踢脚", "嵌条", "收口")):
        return float(hm.group(1))
    return None


def parse_flat_width_mm(name: str, feature: str = "") -> Optional[float]:
    """平板/卡条类线条的可见宽度（无展开面时的兜底口径）。"""
    text = f"{name} {feature}"
    m = WIDTH_BEFORE_RE.search(text) or WIDTH_AFTER_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    if not raw:
        return None
    val = float(raw)
    # 宽度口径只用于细条（>200mm 多为板/饰面，交其它层处理）
    if val <= 0 or val > 200:
        return None
    return val


def is_metal_trim_candidate(name: str, feature: str = "", unit: str = "") -> bool:
    u = normalize_unit(unit)
    if u not in ("m", "米"):
        return False
    text = f"{name} {feature}"
    unfold = parse_unfold_mm(name, feature)
    metal_terms = ("不锈钢", "古铜", "收口", "线条", "装饰线", "嵌条", "MT-", "MT－", "铜条", "AL-", "收边")
    if unfold is not None and any(k in text for k in metal_terms):
        if any(k in text for k in ("柜", "门套", "门头", "屏风", "服务台", "吧台", "洗手台")):
            return False
        return True
    if any(k in text for k in _SKIP_KEYWORDS):
        return False
    if re.search(r"CT-\d+", text, re.I) and "踢脚" in text and ("瓷砖" in text or "CT" in text):
        return False
    if any(k in text for k in ("石膏", "玻镁", "阻燃板", "基层板", "木夹板", "夹板")):
        return False
    if unfold is not None:
        return True
    keys = ("不锈钢", "古铜", "踢脚", "收口", "线条", "装饰线", "嵌条", "MT-", "MT－", "铜条", "AL-", "收边")
    if re.search(r"MT\d", text, re.I):
        return True
    return any(k in text for k in keys)


def _interpolate(samples: List[Tuple[float, dict]], unfold: float) -> Optional[dict]:
    if not samples:
        return None
    samples = sorted(samples, key=lambda x: x[0])
    for w, comps in samples:
        if abs(w - unfold) < 0.5:
            return dict(comps)
    if unfold <= samples[0][0]:
        return dict(samples[0][1])
    if unfold >= samples[-1][0]:
        return dict(samples[-1][1])
    for (w0, c0), (w1, c1) in zip(samples, samples[1:]):
        if w0 <= unfold <= w1:
            ratio = (unfold - w0) / (w1 - w0) if w1 != w0 else 0.5
            out = {}
            for k in ("material_main", "material_aux", "labor", "machinery", "material_loss_rate"):
                v0 = float(c0.get(k) or 0)
                v1 = float(c1.get(k) or 0)
                out[k] = round(v0 + (v1 - v0) * ratio, 2)
            return out
    return None


def _load_width_samples(repo: KnowledgeRepository, ctx: PricingContext) -> List[Tuple[float, dict]]:
    conn = repo.conn()
    try:
        rows = conn.execute(
            """SELECT si.name_norm, si.method_summary, lpf.material_main, lpf.material_aux, lpf.labor,
                      lpf.machinery, lpf.material_loss_rate, lpf.cost_unit_price
               FROM line_price_facts lpf
               JOIN standard_items si ON si.id = lpf.standard_item_id
               WHERE COALESCE(lpf.city,'') = ? AND COALESCE(lpf.price_tier,'mid') = ?
                 AND si.unit_norm IN ('m', '米')""",
            (ctx.city or "", ctx.price_tier or "mid"),
        ).fetchall()
    finally:
        conn.close()
    samples: List[Tuple[float, dict]] = []
    for r in rows:
        _n = r["name_norm"] or ""
        _f = r["method_summary"] or ""
        w = parse_unfold_mm(_n, _f)
        if w is None:
            w = parse_flat_width_mm(_n, _f)
        if w is None:
            continue
        mm = float(r["material_main"] or 0)
        if mm <= 0 or mm > 200:
            continue
        samples.append(
            (
                w,
                {
                    "material_main": mm,
                    "material_aux": float(r["material_aux"] or 0),
                    "labor": float(r["labor"] or 0),
                    "machinery": float(r["machinery"] or 0),
                    "material_loss_rate": float(r["material_loss_rate"] or 0),
                },
            )
        )
    return samples


def _fallback_parametric(unfold: float) -> dict:
    """无样本时按珠海中档经验线性估算（主材≈0.47×展开面+3）。"""
    mat = round(0.468 * unfold + 3.27, 2)
    labor = 12.0 if unfold < 70 else 15.0
    return {
        "material_main": mat,
        "material_aux": 0.3,
        "labor": labor,
        "machinery": 0.2,
        "material_loss_rate": 0.0,
    }


def lookup_metal_trim_price(
    name: str,
    feature: str,
    unit: str,
    repo: KnowledgeRepository,
    ctx: Optional[PricingContext],
) -> Tuple[Optional[dict], str]:
    if not is_metal_trim_candidate(name, feature, unit):
        return None, ""
    text = f"{name} {feature}"
    
    # 先检查是否是踢脚线类项目（避免高度被误识别为展开面）
    if "踢脚" in text or "AL-" in text:
        is_wood = "木" in text or "木质" in text
        if is_wood:
            return (
                {
                    "material_main": 29.2,  # 实际样本校准
                    "material_aux": 2.0,
                    "labor": 6.97,  # 实际样本校准
                    "machinery": 0.2,
                    "material_loss_rate": 0.0,
                },
                "[木踢脚线] 实际样本校准",
            )
    
    # 铝合金装饰线条按截面单列（深圳幕墙样例 4 条各一档，无展开面）。
    # 不走下方泛化 28/10 死值，否则 30*30 被判成 28/10。
    if "铝合金装饰线条" in text:
        section = re.search(r"(\d+)\s*[*×xX]\s*(\d+)\s*mm", text)
        if section:
            a, b = int(section.group(1)), int(section.group(2))
            key = tuple(sorted((a, b)))
            alu_rates = {
                (20, 20): 12.2,
                (20, 50): 20.42,
                (30, 30): 18.2,
                (30, 50): 23.94,
            }
            mat = alu_rates.get(key)
            if mat is not None:
                return (
                    {
                        "material_main": mat,
                        "material_aux": 3.5,
                        "labor": 25.0,
                        "machinery": 0.0,
                        "material_loss_rate": 0.02,
                    },
                    f"[铝合金装饰线条{a}*{b}mm] 实际样本校准",
                )

    unfold = parse_unfold_mm(name, feature)
    if unfold is not None:
        samples: List[Tuple[float, dict]] = []
        if ctx and ctx.city:
            samples = _load_width_samples(repo, ctx)
        comps = _interpolate(samples, unfold) if samples else None
        if not comps:
            comps = _fallback_parametric(unfold)
            note = f"[展开面{unfold:.0f}mm] 参数估算（样本{len(samples)}条）"
        else:
            note = f"[展开面{unfold:.0f}mm] 价库插值（样本{len(samples)}条）"
        return comps, note

    if "铜条" in text:
        return (
            {
                "material_main": 19.0,
                "material_aux": 0.3,
                "labor": 12.0,
                "machinery": 0.2,
                "material_loss_rate": 0.0,
            },
            "[实心铜条] 经验单价（无展开面）",
        )
    if "收边" in text and "踢脚" not in text and "AL-" not in text:
        if re.search(r"5\s*mm|5mm", text):
            # 实际样本校准：5mm不锈钢收边条（门槛石交界处）实_主材12.83/辅材6.41/人工12.19/机械0.64
            return (
                {
                    "material_main": 12.83,
                    "material_aux": 6.41,
                    "labor": 12.19,
                    "machinery": 0.64,
                    "material_loss_rate": 0.0,
                },
                "[5mm不锈钢收边条] 实际样本校准",
            )
        # 实际样本校准：3mm墙面金属收边条实_主材10.57,实_人工16.83
        if re.search(r"3\s*mm|3mm", text):
            return (
                {
                    "material_main": 10.57,
                    "material_aux": 1.0,
                    "labor": 16.83,
                    "machinery": 0.3,
                    "material_loss_rate": 0.0,
                },
                "[3mm金属收边条] 实际样本校准",
            )
        return (
            {
                "material_main": 6.0,
                "material_aux": 0.5,
                "labor": 5.0,
                "machinery": 0.2,
                "material_loss_rate": 0.0,
            },
            "[金属收边条] 经验单价",
        )
    if any(k in text for k in ("踢脚", "AL-", "收口", "嵌条")):
        # 实际样本校准：
        # 木踢脚线（50mm高）：主材29.2-34.2，人工6.97
        # AL-03黑色型材踢脚线（20mm高）：主材15.9-17.79，人工12-12.93
        is_wood = "木" in text or "木质" in text
        if is_wood:
            return (
                {
                    "material_main": 29.2,  # 实际样本校准
                    "material_aux": 2.0,
                    "labor": 6.97,  # 实际样本校准
                    "machinery": 0.2,
                    "material_loss_rate": 0.0,
                },
                "[木踢脚线] 实际样本校准（无展开面）",
            )
        else:
            return (
                {
                    "material_main": 22.0,
                    "material_aux": 2.0,
                    "labor": 8.0,
                    "machinery": 0.2,
                    "material_loss_rate": 0.0,
                },
                "[型材踢脚/收边] 经验单价（无展开面）",
            )
    # 无展开面的 MT/装饰线
    if re.search(r"MT-0?\d|MT\d", text, re.I) or "装饰线" in text:
        # 清单只给可见宽度（如"5mm宽不锈钢卡条"、"3mm金属线条（宽10mm）"）：
        # 按宽度插值，避免泛化 28/10 死值
        width = parse_flat_width_mm(name, feature)
        if width is not None:
            samples: List[Tuple[float, dict]] = []
            if ctx and ctx.city:
                samples = _load_width_samples(repo, ctx)
            comps = _interpolate(samples, width) if samples else None
            if not comps:
                comps = _fallback_parametric(width)
                note = f"[宽度{width:.0f}mm] 参数估算（样本{len(samples)}条）"
            else:
                note = f"[宽度{width:.0f}mm] 价库插值（样本{len(samples)}条）"
            return comps, note
        # 实际样本校准：
        # MT02黑色铝条：主材28，人工10
        # MT01黑色铝条15*15mm：主材28，人工12
        return (
            {
                "material_main": 28.0,  # 实际样本校准
                "material_aux": 3.0,
                "labor": 10.0,  # 实际样本校准
                "machinery": 0.2,
                "material_loss_rate": 0.0,
            },
            "[金属装饰线/MT] 实际样本校准",
        )
    return None, ""
