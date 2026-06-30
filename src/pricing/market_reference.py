"""公开市场参考价（无历史样本或工艺价型失真时兜底）。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from src.normalize.text import normalize_name, normalize_unit

_CACHE: Optional[dict] = None


def _load() -> dict:
    global _CACHE
    if _CACHE is None:
        p = Path(__file__).resolve().parents[2] / "config" / "market_reference_prices.json"
        _CACHE = json.loads(p.read_text(encoding="utf-8"))
    return _CACHE


@dataclass
class MarketRef:
    rule_id: str
    material_main: float
    material_aux: float
    labor: float
    machinery: float
    material_loss_rate: float = 0.0
    note: str = ""
    confidence: float = 0.82


def lookup_market_reference(
    name: str,
    feature: str = "",
    unit: str = "",
    *,
    city: str = "",
    tier: str = "mid",
) -> Optional[MarketRef]:
    """按名称+特征+单位匹配市场参考规则（越具体优先级越高）。"""
    cfg = _load()
    name_n = normalize_name(name)
    feat_n = normalize_name(feature)
    combined = f"{name_n}\n{feat_n}"
    unit_n = normalize_unit(unit)
    if not unit_n:
        return None

    best: Optional[MarketRef] = None
    best_score = 0.0

    for rule in cfg.get("rules", []):
        score = 0.0
        allowed = rule.get("units") or []
        if allowed and unit_n not in allowed:
            continue

        name_hits = 0
        for kw in rule.get("name_keywords", []):
            kn = normalize_name(kw)
            if kn and kn in name_n:
                name_hits += 1
                score += 15 + len(kn) * 0.1
        if rule.get("name_keywords") and name_hits == 0:
            continue

        feat_req = rule.get("feature_keywords") or []
        feat_hits = 0
        for kw in feat_req:
            kn = normalize_name(kw)
            if kn and kn in combined:
                feat_hits += 1
                score += 8 + len(kn) * 0.05
        if feat_req and rule.get("require_feature_keywords") and feat_hits == 0:
            continue
        if feat_req and not feat_n:
            continue

        for kw in rule.get("exclude_feature_keywords", []):
            kn = normalize_name(kw)
            if kn and kn in feat_n:
                score = 0.0
                break
        if score <= 0:
            continue

        for kw in rule.get("exclude_name_keywords", []):
            kn = normalize_name(kw)
            if kn and kn in name_n:
                score = 0.0
                break
        if score <= 0:
            continue

        # 无机涂料 ≡ 乳胶漆：名称只写「无机涂料」时仍可命中仅含「乳胶漆」的规则
        if score > 0 and "无机涂料" in combined and "乳胶漆" not in combined:
            for kw in rule.get("name_keywords", []):
                if "乳胶漆" in normalize_name(kw):
                    score += 3
                    break

        if score <= 0:
            continue
        if score > best_score:
            best_score = score
            best = MarketRef(
                rule_id=rule["id"],
                material_main=float(rule.get("material_main", 0)),
                material_aux=float(rule.get("material_aux", 0)),
                labor=float(rule.get("labor", 0)),
                machinery=float(rule.get("machinery", 0)),
                material_loss_rate=float(rule.get("material_loss_rate", 0)),
                note=rule.get("source_note", "市场参考价"),
                confidence=float(rule.get("confidence", 0.82)),
            )

    return best
