"""从项目特征/做法描述中提取结构化标签 — 组价匹配的核心。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.normalize.text import normalize_feature, normalize_name

_RULES_CACHE: Optional[dict] = None


def _load_rules() -> dict:
    global _RULES_CACHE
    if _RULES_CACHE is None:
        p = Path(__file__).resolve().parents[2] / "config" / "feature_rules.json"
        _RULES_CACHE = json.loads(p.read_text(encoding="utf-8"))
    return _RULES_CACHE


@dataclass
class FeatureProfile:
    """一条清单项的特征画像。"""
    tags: Dict[str, str] = field(default_factory=dict)
    labels: List[str] = field(default_factory=list)
    thickness_mm: List[str] = field(default_factory=list)

    def signature(self) -> str:
        """归并键：同名同单位下区分做法。"""
        parts = [f"{k}:{v}" for k, v in sorted(self.tags.items())]
        if self.thickness_mm:
            parts.append("thk:" + ",".join(sorted(set(self.thickness_mm))))
        return "|".join(parts) if parts else "_generic"

    def summary(self) -> str:
        """给人看的做法摘要。"""
        if self.labels:
            return "；".join(self.labels[:8])
        if self.thickness_mm:
            return "厚度 " + "/".join(self.thickness_mm) + "mm"
        return "（未识别具体做法，按全文匹配）"


def extract_feature_profile(
    feature: str,
    name: str = "",
) -> FeatureProfile:
    rules = _load_rules()
    text = normalize_feature(feature)
    name_n = normalize_name(name)
    combined = f"{name_n}\n{text}"

    profile = FeatureProfile()
    seen_rule: set[str] = set()

    for rule in rules.get("rules", []):
        rid = rule["id"]
        if rid in seen_rule:
            continue
        pat = rule["pattern"]
        if re.search(pat, combined, re.IGNORECASE | re.MULTILINE):
            key, val = rule["key"], rule["value"]
            if key not in profile.tags:
                profile.tags[key] = val
                profile.labels.append(rule.get("label", f"{key}={val}"))
            seen_rule.add(rid)

    for m in re.finditer(rules.get("thickness_pattern", r"(\d+)\s*mm"), combined, re.I):
        profile.thickness_mm.append(m.group(1))
        if "plaster_thickness_mm" not in profile.tags and (
            "抹灰" in combined or "找平" in combined or "砂浆" in combined
        ):
            profile.tags["plaster_thickness_mm"] = m.group(1)

    for hint_name, keys in rules.get("name_hints", {}).items():
        if hint_name in name_n:
            for k in keys:
                if k not in profile.tags and k == "paint_coats":
                    if "三遍" in combined or "3遍" in combined:
                        profile.tags["paint_coats"] = "3"
                        profile.labels.append("乳胶漆三遍")
                    elif "两遍" in combined or "2遍" in combined or "二遍" in combined:
                        profile.tags["paint_coats"] = "2"
                        profile.labels.append("乳胶漆两遍")

    return profile


def compare_profiles(
    query: FeatureProfile,
    target: FeatureProfile,
    critical_keys: Optional[List[str]] = None,
) -> Tuple[float, List[str]]:
    """
    比较做法一致性。
    返回 (标签一致度 0~1, 冲突说明列表)。
    关键标签不一致 → 一致度封顶 0.45 并记录冲突。
    """
    rules = _load_rules()
    critical = set(critical_keys or rules.get("critical_keys", []))
    conflicts: List[str] = []
    all_keys = set(query.tags) | set(target.tags)
    if not all_keys:
        return 1.0, []

    match = 0
    total = 0
    for k in all_keys:
        qv, tv = query.tags.get(k), target.tags.get(k)
        if qv is None or tv is None:
            continue
        total += 1
        if qv == tv:
            match += 1
        elif k in critical:
            label_map = {r["key"]: r.get("label", k) for r in rules.get("rules", [])}
            conflicts.append(
                f"做法冲突[{k}]：本条「{qv}」≠ 历史「{tv}」"
            )
        else:
            match += 0.3

    ratio = match / total if total else 1.0
    if conflicts:
        ratio = min(ratio, 0.45)
    return ratio, conflicts


def method_signature_from_text(feature: str, name: str = "") -> str:
    return extract_feature_profile(feature, name).signature()


def feature_summary_text(feature: str, name: str = "") -> str:
    return extract_feature_profile(feature, name).summary()
