"""清单项 → 工艺类型 / 专业（装饰、机电）识别。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.normalize.text import normalize_name, normalize_unit

_RULES_CACHE: Optional[dict] = None


def _load_rules() -> dict:
    global _RULES_CACHE
    if _RULES_CACHE is None:
        p = Path(__file__).resolve().parents[2] / "config" / "craft_trade_rules.json"
        _RULES_CACHE = json.loads(p.read_text(encoding="utf-8"))
    return _RULES_CACHE


@dataclass
class CraftMatch:
    craft_id: str
    trade: str
    label: str
    score: float
    expects: Dict[str, int]
    template_share: Dict[str, float]
    tag_keys: List[str]


def classify_craft(name: str, feature: str = "", unit: str = "") -> CraftMatch:
    """按关键词匹配工艺类型；未命中则 generic_finish。"""
    rules = _load_rules()
    name_n = normalize_name(name)
    feat_n = normalize_name(feature)
    combined = f"{name_n}{feat_n}"
    unit_n = normalize_unit(unit)

    best: Optional[CraftMatch] = None
    best_score = 0.0

    for craft in rules.get("crafts", []):
        if craft.get("id") == "generic_finish":
            continue
        allowed = craft.get("units") or []
        if allowed and unit_n and unit_n not in allowed:
            continue
        score = float(craft.get("priority") or 0)
        name_hit = False
        for kw in craft.get("keywords", []):
            kn = normalize_name(kw)
            if not kn:
                continue
            if kn in name_n:
                score += 10 + len(kn) * 0.1
                name_hit = True
            elif kn in combined:
                score += 5 + len(kn) * 0.05
        feat_req = craft.get("feature_keywords") or []
        if feat_req:
            feat_hit = any(normalize_name(k) in combined for k in feat_req if k)
            if not feat_hit:
                continue
            score += 20 + len(feat_req) * 3
        elif not name_hit:
            continue
        if score > best_score:
            best_score = score
            best = CraftMatch(
                craft_id=craft["id"],
                trade=craft.get("trade", "decoration"),
                label=craft.get("label", craft["id"]),
                score=score,
                expects=dict(craft.get("expects", {})),
                template_share=dict(craft.get("template_share", {})),
                tag_keys=list(craft.get("tag_keys", [])),
            )

    if best:
        return best

    generic = next(
        (c for c in rules.get("crafts", []) if c.get("id") == "generic_finish"),
        None,
    )
    if generic:
        return CraftMatch(
            craft_id="generic_finish",
            trade="decoration",
            label=generic.get("label", "装饰综合"),
            score=0.1,
            expects=dict(generic.get("expects", {})),
            template_share=dict(generic.get("template_share", {})),
            tag_keys=[],
        )
    return CraftMatch(
        craft_id="unknown",
        trade="decoration",
        label="未分类",
        score=0.0,
        expects={"material_main": 1, "material_aux": 1, "labor": 1, "machinery": 0},
        template_share={"main": 0.4, "aux": 0.2, "labor": 0.36, "machinery": 0.02},
        tag_keys=[],
    )


def get_craft_rules() -> dict:
    return _load_rules()
