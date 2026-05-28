"""涂料等价：定额与市场口径下「无机涂料」≈「乳胶漆」（同工序、同价库）。"""
from __future__ import annotations

from typing import List

from rapidfuzz import fuzz

from src.normalize.text import normalize_name

# 组价/套价时视为同一类面层涂料
PAINT_SURFACE_ALIASES = (
    "无机涂料",
    "乳胶漆",
    "无机矿物涂料",
    "内墙涂料",
    "天棚涂料",
    "墙面涂料",
    "涂料饰面",
    "白色涂料",
)

PAINT_FEATURE_HINTS = (
    "腻子",
    "底漆",
    "面漆",
    "涂刷",
    "两遍",
    "三遍",
)


def is_paint_item(name: str, feature: str = "") -> bool:
    t = normalize_name(name) + normalize_name(feature)
    return any(k in t for k in PAINT_SURFACE_ALIASES)


def paint_name_variants(text: str) -> List[str]:
    """生成乳胶漆↔无机涂料等价写法，用于匹配与查价。"""
    s = normalize_name(text)
    if not s:
        return [""]
    out = {s}
    if "无机涂料" in s:
        out.add(s.replace("无机涂料", "乳胶漆"))
    if "乳胶漆" in s:
        out.add(s.replace("乳胶漆", "无机涂料"))
    return list(out)


def paint_name_match_score(name_a: str, name_b: str) -> float:
    """名称相似度；涂料类自动尝试乳胶漆/无机涂料互换。"""
    na, nb = normalize_name(name_a), normalize_name(name_b)
    if not na or not nb:
        return 0.0
    best = fuzz.token_set_ratio(na, nb) / 100.0
    if is_paint_item(name_a) or is_paint_item(name_b):
        for va in paint_name_variants(na):
            for vb in paint_name_variants(nb):
                best = max(best, fuzz.token_set_ratio(va, vb) / 100.0)
    return best


def paint_catalog_note() -> str:
    return "定额口径：无机涂料与乳胶漆同属涂料面层，组价可互套历史乳胶漆价或定额乳胶漆子目。"
