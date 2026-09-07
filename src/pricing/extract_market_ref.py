# -*- coding: utf-8 -*-
"""
市场参考价自动提炼工具。
从知识库（cost_records）聚合跨项目一致样本簇，生成可审核的市场参考价候选规则。
输出 JSON 到 data/exports/market_ref_candidates.json，人工审核后合并进
config/market_reference_prices.json。

用法：python app.py extract-market-ref [--top N] [--min-projects N] [--city 深圳]
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Tuple

from src.db.database import get_connection
from src.normalize.text import normalize_name, normalize_unit
from src.pricing.market_reference import lookup_market_reference

ROOT = Path(__file__).resolve().parents[2]
EXPORT_DIR = ROOT / "data" / "exports"

FEE_KEYS = (
    "安全文明", "安全生产责任险", "材料搬运", "设计出图", "总承包服务",
    "成品保护", "试验费", "检验费", "检测费", "垃圾清运", "排污",
)
SKIP_WORDS = (
    "新增", "更换", "拆除", "铲除", "维修", "零星", "暂估", "甲供",
    "利旧", "改造", "配合费", "总价措施", "规费", "税金",
)
# 项目内材料代号前缀（ST/CT/WD 等物料书代号不跨项目；MT 为材质代号可保留，但需多项目确认）
CODE_PREFIXES = r"(st|ct|wd|pt|cl|up|sf|vf|mr|mt|py|js|fj|dt|kt|xf|zj|jk|sc|rc|wc|wz|nh|nhyjv|yjv|bv|bttz|wdzn|jdg|dn)\d*[a-z0-9-]*"


def _strip_spec(name: str) -> str:
    """名称 → 核心做法词：去括号/规格数字/项目编号，仅留中文核心词。"""
    n = (name or "").lower().replace(" ", "").replace("\u3000", "")
    n = re.sub(r"[（(].*?[)）]", "", n)
    n = re.sub(r"[0-9.×x*+]+", "", n)
    n = re.sub(CODE_PREFIXES, "", n, flags=re.I)
    n = re.sub(r"[^\u4e00-\u9fa5a-z/·]", "", n)
    return n


def load_samples(db_path: Optional[str] = None) -> List[dict]:
    """加载排除模拟清单/费用项后的真实样本。"""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT cr.source_project_id, p.name AS proj, p.city, p.price_tier,
                   bl.name, bl.feature, bl.unit,
                   cr.material_main, cr.material_aux, cr.labor, cr.machinery,
                   cr.material_loss_rate, cr.cost_unit_price
            FROM cost_records cr
            JOIN projects p ON p.id = cr.source_project_id
            LEFT JOIN boq_lines bl ON bl.id = cr.source_line_id
            WHERE p.name NOT LIKE '%附件2%' AND p.name NOT LIKE '%模拟%'
            """
        ).fetchall()
    finally:
        conn.close()

    samples = []
    for r in rows:
        name = r["name"] or ""
        if not name or not r["unit"] or not r["city"]:
            continue
        if any(k in name for k in FEE_KEYS):
            continue
        samples.append(
            {
                "proj": r["proj"], "city": r["city"], "tier": r["price_tier"],
                "name": name, "feature": r["feature"] or "", "unit": r["unit"],
                "material_main": r["material_main"] or 0,
                "material_aux": r["material_aux"] or 0,
                "labor": r["labor"] or 0, "machinery": r["machinery"] or 0,
                "loss": r["material_loss_rate"] or 0,
                "cost_total": r["cost_unit_price"] or 0,
            }
        )
    return samples


def cluster_candidates(
    samples: List[dict],
    *,
    min_n: int = 3,
    min_projects: int = 2,
    max_uniq_values: int = 3,
    min_top_ratio: float = 0.7,
    max_spread: float = 0.35,
) -> List[dict]:
    """按 城市+核心词+单位 聚合，过滤出可用候选簇。"""
    groups: Dict[Tuple[str, str, str], List[dict]] = defaultdict(list)
    for s in samples:
        words = _strip_spec(s["name"])
        if len(words) < 4 or any(w in words for w in SKIP_WORDS):
            continue
        key = (s["city"], words, normalize_unit(s["unit"]) or "")
        groups[key].append(s)

    cands: List[dict] = []
    for (city, words, unit), items in groups.items():
        if len(items) < min_n:
            continue
        projs = {it["proj"] for it in items}
        if len(projs) < min_projects:
            continue
        mains = sorted(it["material_main"] for it in items)
        m0 = median(mains)
        if m0 <= 0:
            continue
        dist = Counter(mains)
        top_cnt = dist.most_common(1)[0][1]
        if len(dist) > max_uniq_values or top_cnt / len(mains) < min_top_ratio:
            continue
        if (mains[-1] - mains[0]) / m0 > max_spread:
            continue
        cands.append(
            {
                "city": city,
                "words": words,
                "unit": unit,
                "n": len(items),
                "projs": sorted(projs),
                "main_median": round(m0, 2),
                "main_dist": {str(k): v for k, v in dist.most_common(6)},
                "aux_median": round(median(it["material_aux"] for it in items), 2),
                "lab_median": round(median(it["labor"] for it in items), 2),
                "mach_median": round(median(it["machinery"] for it in items), 2),
                "loss_median": round(median(it["loss"] for it in items), 3),
                "cost_median": round(median(it["cost_total"] for it in items), 2),
            }
        )
    cands.sort(key=lambda c: (-len(c["projs"]), -c["n"]))
    return cands


def check_existing_hit(cand: dict) -> bool:
    """候选是否已被现有 market_reference 规则命中（避免重复/冲突）。"""
    hit = lookup_market_reference(
        cand["words"], feature="", unit=cand["unit"], city=cand["city"]
    )
    return hit is not None


def build_report(
    db_path: Optional[str] = None,
    *,
    min_n: int = 3,
    min_projects: int = 2,
    top: Optional[int] = None,
    city: Optional[str] = None,
) -> Dict:
    samples = load_samples(db_path)
    cands = cluster_candidates(samples, min_n=min_n, min_projects=min_projects)
    if city:
        cands = [c for c in cands if c["city"] == city]
    if top:
        cands = cands[:top]
    for c in cands:
        c["already_covered"] = check_existing_hit(c)
    report = {
        "generated": "extract-market-ref",
        "params": {"min_n": min_n, "min_projects": min_projects, "city": city},
        "total_samples": len(samples),
        "candidates": cands,
    }
    return report


def export_report(report: Dict, path: Optional[Path] = None) -> Path:
    out = path or EXPORT_DIR / "market_ref_candidates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out
