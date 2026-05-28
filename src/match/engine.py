"""相同清单项识别：做法标签 + 特征全文 + 精确/模糊模式。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from rapidfuzz import fuzz

from src.normalize.feature_extract import (
    FeatureProfile,
    compare_profiles,
    extract_feature_profile,
)
from src.normalize.paint_equiv import paint_name_match_score
from src.normalize.text import normalize_feature, normalize_name, normalize_unit


class MatchMode(str, Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    AUTO = "auto"


@dataclass
class MatchCandidate:
    standard_item_id: int
    name_norm: str
    feature_norm: str
    unit_norm: str
    method_signature: str
    method_summary: str
    name_score: float
    feature_score: float
    tag_score: float
    total_score: float
    sample_count: int
    match_type: str
    tag_conflicts: List[str]


@dataclass
class MatchThresholds:
    exact_name: float = 0.98
    exact_feature: float = 0.92
    exact_tag: float = 0.95
    fuzzy_name: float = 0.85
    fuzzy_feature: float = 0.75
    fuzzy_tag: float = 0.80
    fuzzy_min_total: float = 0.72
    reference_min_total: float = 0.55
    name_weight: float = 0.20
    feature_weight: float = 0.35
    tag_weight: float = 0.45

    @classmethod
    def from_config(cls, cfg: dict) -> "MatchThresholds":
        ex = cfg.get("exact", {})
        fu = cfg.get("fuzzy", {})
        w = cfg.get("weights", {})
        return cls(
            exact_name=ex.get("name_min", 0.98),
            exact_feature=ex.get("feature_min", 0.90),
            exact_tag=ex.get("tag_min", 0.95),
            fuzzy_name=fu.get("name_min", 0.85),
            fuzzy_feature=fu.get("feature_min", 0.70),
            fuzzy_tag=fu.get("tag_min", 0.75),
            fuzzy_min_total=fu.get("total_min", 0.72),
            reference_min_total=fu.get("reference_min", 0.55),
            name_weight=w.get("name", 0.20),
            feature_weight=w.get("feature", 0.35),
            tag_weight=w.get("tag", 0.45),
        )


def _profile_from_row(row: dict, feature: str, name: str) -> FeatureProfile:
    if row.get("feature_tags_json"):
        try:
            tags = json.loads(row["feature_tags_json"])
            p = FeatureProfile(tags=tags)
            if row.get("method_summary"):
                p.labels = [row["method_summary"]]
            return p
        except json.JSONDecodeError:
            pass
    return extract_feature_profile(feature or row.get("feature_norm", ""), name or row.get("name_norm", ""))


def score_pair(
    name_a: str,
    feature_a: str,
    unit_a: str,
    name_b: str,
    feature_b: str,
    unit_b: str,
    *,
    th: MatchThresholds,
    profile_a: Optional[FeatureProfile] = None,
    profile_b: Optional[FeatureProfile] = None,
) -> Optional[Tuple[float, float, float, float, List[str]]]:
    ua, ub = normalize_unit(unit_a), normalize_unit(unit_b)
    if not ua or not ub or ua != ub:
        return None

    pa = profile_a or extract_feature_profile(feature_a, name_a)
    pb = profile_b or extract_feature_profile(feature_b, name_b)

    na, nb = normalize_name(name_a), normalize_name(name_b)
    fa, fb = normalize_feature(feature_a), normalize_feature(feature_b)
    ns = fuzz.token_set_ratio(na, nb) / 100.0
    ns = max(ns, paint_name_match_score(name_a, name_b))
    fs = (
        fuzz.token_set_ratio(fa, fb) / 100.0
        if (fa or fb)
        else (1.0 if not fa and not fb else 0.0)
    )
    ts, conflicts = compare_profiles(pa, pb)

    total = th.name_weight * ns + th.feature_weight * fs + th.tag_weight * ts
    return ns, fs, ts, total, conflicts


def is_exact(ns: float, fs: float, ts: float, th: MatchThresholds, conflicts: List[str]) -> bool:
    if conflicts:
        return False
    return ns >= th.exact_name and fs >= th.exact_feature and ts >= th.exact_tag


def is_fuzzy(
    ns: float, fs: float, ts: float, total: float, th: MatchThresholds, conflicts: List[str]
) -> bool:
    if conflicts:
        return False
    if is_exact(ns, fs, ts, th, conflicts):
        return True
    return (
        ns >= th.fuzzy_name
        and fs >= th.fuzzy_feature
        and ts >= th.fuzzy_tag
        and total >= th.fuzzy_min_total
    )


def classify_level(
    ns: float,
    fs: float,
    ts: float,
    total: float,
    th: MatchThresholds,
    mode: MatchMode,
    conflicts: List[str],
) -> str:
    if conflicts:
        return "C" if total >= th.reference_min_total else "D"
    if is_exact(ns, fs, ts, th, conflicts):
        return "A"
    if mode == MatchMode.EXACT:
        return "C" if total >= th.reference_min_total else "D"
    if is_fuzzy(ns, fs, ts, total, th, conflicts):
        return "B"
    if total >= th.reference_min_total:
        return "C"
    return "D"


def should_auto_fill(level: str, mode: MatchMode, conflicts: List[str]) -> bool:
    if conflicts:
        return False
    if level == "D":
        return False
    if mode == MatchMode.EXACT:
        return level == "A"
    if mode == MatchMode.FUZZY:
        return level in ("A", "B")
    return level in ("A", "B")


def rank_candidates(
    name: str,
    feature: str,
    unit: str,
    pool: Sequence[dict],
    *,
    top_n: int = 5,
    th: Optional[MatchThresholds] = None,
    mode: MatchMode = MatchMode.AUTO,
) -> List[MatchCandidate]:
    if th is None:
        th = MatchThresholds()
    q_prof = extract_feature_profile(feature, name)
    results: List[MatchCandidate] = []

    for row in pool:
        t_prof = _profile_from_row(row, row.get("feature_norm", ""), row.get("name_norm", ""))
        scored = score_pair(
            name,
            feature,
            unit,
            row["name_norm"],
            row.get("feature_norm") or "",
            row["unit_norm"],
            th=th,
            profile_a=q_prof,
            profile_b=t_prof,
        )
        if scored is None:
            continue
        ns, fs, ts, total, conflicts = scored
        mtype = "exact" if is_exact(ns, fs, ts, th, conflicts) else "fuzzy"
        results.append(
            MatchCandidate(
                standard_item_id=row["id"],
                name_norm=row["name_norm"],
                feature_norm=row.get("feature_norm") or "",
                unit_norm=row["unit_norm"],
                method_signature=row.get("method_signature") or t_prof.signature(),
                method_summary=row.get("method_summary") or t_prof.summary(),
                name_score=ns,
                feature_score=fs,
                tag_score=ts,
                total_score=total,
                sample_count=int(row.get("sample_count") or 0),
                match_type=mtype,
                tag_conflicts=conflicts,
            )
        )
    results.sort(
        key=lambda x: (
            -x.total_score,
            -x.tag_score,
            -int(x.match_type == "exact"),
            -x.sample_count,
        )
    )
    return results[:top_n]


def best_match(
    name: str,
    feature: str,
    unit: str,
    pool: Sequence[dict],
    *,
    th: Optional[MatchThresholds] = None,
    mode: MatchMode = MatchMode.AUTO,
) -> Tuple[Optional[MatchCandidate], str]:
    cands = rank_candidates(name, feature, unit, pool, top_n=1, th=th, mode=mode)
    if not cands:
        return None, "D"
    c = cands[0]
    if th is None:
        th = MatchThresholds()
    level = classify_level(
        c.name_score, c.feature_score, c.tag_score, c.total_score, th, mode, c.tag_conflicts
    )
    return c, level
