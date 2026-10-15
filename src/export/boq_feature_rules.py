# -*- coding: utf-8 -*-
"""清单特征必查字段与同类单价离散检查。

规则来源：jayden-lg/costing-master references/boq-check-rules.md（MIT）。
只出疑似问题，不回写清单、不定价。
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.ingest.line_types import ParsedLine, cell_str

# (专业, 名称触发词, 特征必查词组)。词组内任一命中即视为该字段已描述。
FEATURE_RULES: Tuple[Tuple[str, Tuple[str, ...], Tuple[Tuple[str, ...], ...]], ...] = (
    ("土方", ("土方", "挖土", "回填"), (
        ("土类别",), ("挖", "填"), ("运距", "运输"), ("弃土", "回填"),
    )),
    ("混凝土", ("混凝土", "砼"), (
        ("C15", "C20", "C25", "C30", "C35", "C40", "强度"),
        ("部位", "柱", "梁", "板", "墙", "基础"),
    )),
    ("砌体", ("砌块", "砌体", "砌筑"), (
        ("加气", "砖", "砌块", "材料"), ("M5", "M7.5", "M10", "砂浆"), ("厚",),
    )),
    ("防水", ("防水",), (
        ("卷材", "涂膜", "涂料", "砂浆", "材料"), ("厚", "道"), ("屋面", "楼面", "墙", "部位"),
    )),
    ("门窗", ("门", "窗"), (
        ("木", "钢", "铝", "玻璃", "材质"), ("平开", "推拉", "开启"),
    )),
    ("装饰面层", ("楼地面", "墙面", "吊顶", "天棚", "踢脚", "涂料", "腻子"), (
        ("石", "砖", "板", "涂料", "腻子", "铝", "面层"), ("厚", "规格"),
    )),
    ("给排水管", ("给水管", "排水管", "管道"), (
        ("PPR", "PVC", "钢管", "铸铁", "材质"), ("DN", "De", "Φ", "规格"), ("连接", "热熔", "粘接"),
    )),
    ("电缆电线", ("电缆", "电线", "配线"), (
        ("ZR", "BV", "YJV", "型号"), ("mm", "规格"), ("敷设", "桥架", "配管", "穿管"),
    )),
    ("风管", ("风管",), (
        ("镀锌", "材质"), ("厚",), ("保温",),
    )),
)

_SKIP_NAME = ("拆除", "垂直运输", "脚手架", "成品保护", "垃圾清运")


@dataclass
class FeatureGap:
    seq: str
    name: str
    trade: str
    missing: Tuple[str, ...]


def _hit(text: str, words: Sequence[str]) -> bool:
    return any(w.lower() in text.lower() for w in words)


def feature_gaps(name: str, feature: str) -> List[Tuple[str, Tuple[str, ...]]]:
    """返回 (专业, 缺失字段)。名称命中拆除/措施类时不查。"""
    if any(k in name for k in _SKIP_NAME):
        return []
    text = f"{name} {feature}"
    out: List[Tuple[str, Tuple[str, ...]]] = []
    for trade, triggers, fields in FEATURE_RULES:
        if not _hit(name, triggers):
            continue
        missing = tuple(group[0] for group in fields if not _hit(text, group))
        if missing:
            out.append((trade, missing))
    return out


def collect_feature_gaps(lines: Iterable[ParsedLine]) -> List[FeatureGap]:
    gaps: List[FeatureGap] = []
    for ln in lines:
        name = cell_str(ln.name)
        if not name:
            continue
        for trade, missing in feature_gaps(name, cell_str(ln.feature)):
            gaps.append(FeatureGap(ln.seq, name, trade, missing))
    return gaps


def _group_key(name: str) -> Optional[str]:
    """只对名称足够具体的同类项分组，避免把不同做法并成一组。"""
    n = re.sub(r"\s+", "", name)
    n = re.sub(r"[（(][^）)]*[）)]", "", n)
    if len(n) < 4 or any(k in n for k in _SKIP_NAME):
        return None
    return n


def price_dispersion(
    lines: Iterable[ParsedLine],
    cv_limit: float = 0.30,
    min_group: int = 3,
) -> List[Dict[str, object]]:
    """同类项综合单价变异系数。CV>30% 且至少 3 条才报疑似。"""
    groups: Dict[str, List[Tuple[str, float]]] = {}
    for ln in lines:
        price = ln.unit_price
        if price is None or price <= 0:
            continue
        key = _group_key(cell_str(ln.name))
        if not key:
            continue
        groups.setdefault(key, []).append((ln.seq, float(price)))

    flagged: List[Dict[str, object]] = []
    for key, pairs in groups.items():
        if len(pairs) < min_group:
            continue
        prices = [p for _, p in pairs]
        mean = statistics.fmean(prices)
        if mean <= 0:
            continue
        cv = statistics.pstdev(prices) / mean
        if cv <= cv_limit:
            continue
        flagged.append({
            "name": key,
            "count": len(pairs),
            "cv": round(cv, 3),
            "min": min(prices),
            "max": max(prices),
            "seqs": [s for s, _ in pairs],
        })
    flagged.sort(key=lambda x: float(x["cv"]), reverse=True)
    return flagged
