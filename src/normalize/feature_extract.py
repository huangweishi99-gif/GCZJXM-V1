"""从项目特征/做法描述中提取结构化标签 — 组价匹配的核心。"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from src.normalize.text import normalize_feature, normalize_name, parse_craft_points

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
    craft_points: List[str] = field(default_factory=list)

    def signature(self) -> str:
        """归并键：同名同单位下区分做法（含逐条施工工艺指纹）。"""
        parts = [f"{k}:{v}" for k, v in sorted(self.tags.items())]
        if self.thickness_mm:
            parts.append("thk:" + ",".join(sorted(set(self.thickness_mm))))
        if self.craft_points:
            joined = "\n".join(self.craft_points)
            h = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
            parts.append(f"craft:{h}")
        return "|".join(parts) if parts else "_generic"

    def summary(self) -> str:
        """给人看的做法摘要。"""
        if self.labels:
            head = "；".join(self.labels[:6])
            if len(self.craft_points) > 1:
                return f"{head}（共{len(self.craft_points)}条工艺）"
            return head
        if self.craft_points:
            preview = "；".join(self.craft_points[:3])
            if len(self.craft_points) > 3:
                preview += f"…等{len(self.craft_points)}条"
            return preview
        if self.thickness_mm:
            return "厚度 " + "/".join(self.thickness_mm) + "mm"
        return "（未识别具体做法，按全文匹配）"


def compare_craft_points(
    query: List[str],
    target: List[str],
    *,
    line_min_ratio: float = 0.82,
) -> Tuple[float, List[str]]:
    """
    逐条比对施工工艺（项目特征每一点 = 一道工序）。
    返回 (0~1 一致度, 冲突说明)。
    """
    conflicts: List[str] = []
    if not query and not target:
        return 1.0, []
    if not query or not target:
        return 0.55, ["特征工艺条目数量不一致，需人工核对"]

    matched = 0
    weak: List[str] = []
    for qp in query:
        best = max((fuzz.token_set_ratio(qp, tp) / 100.0 for tp in target), default=0.0)
        if best >= line_min_ratio:
            matched += 1
        else:
            weak.append(qp[:40])

    ratio = matched / len(query)
    # 目标侧多出的关键工艺（如历史多一道防水）也要提示
    if target and len(target) > len(query):
        extra = len(target) - len(query)
        if extra >= 2:
            conflicts.append(f"历史项多 {extra} 条工艺描述，可能不是同一做法")

    if weak:
        conflicts.append(
            f"有 {len(weak)} 条工艺与历史不一致，如：{'；'.join(weak[:2])}"
        )

    if ratio < 0.65:
        ratio = min(ratio, 0.40)
    elif ratio < 0.85 and conflicts:
        ratio = min(ratio, 0.55)

    return ratio, conflicts


def extract_feature_profile(
    feature: str,
    name: str = "",
) -> FeatureProfile:
    rules = _load_rules()
    text = normalize_feature(feature)
    name_n = normalize_name(name)
    combined = f"{name_n}\n{text}"

    profile = FeatureProfile(craft_points=parse_craft_points(feature))
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
        tag_ratio = 1.0
    else:
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
                conflicts.append(
                    f"做法冲突[{k}]：本条「{qv}」≠ 历史「{tv}」"
                )
            else:
                match += 0.3
        tag_ratio = match / total if total else 1.0

    craft_ratio, craft_conflicts = compare_craft_points(
        query.craft_points, target.craft_points
    )
    conflicts.extend(craft_conflicts)

    # 标签 + 逐条工艺：工艺条目权重更高（造价实务）
    if query.craft_points or target.craft_points:
        ratio = 0.35 * tag_ratio + 0.65 * craft_ratio
    else:
        ratio = tag_ratio

    if conflicts and any("冲突" in c or "不一致" in c for c in conflicts):
        ratio = min(ratio, 0.45)
    elif craft_conflicts and craft_ratio < 0.85:
        ratio = min(ratio, 0.55)

    return ratio, conflicts


def method_signature_from_text(feature: str, name: str = "") -> str:
    return extract_feature_profile(feature, name).signature()


def feature_summary_text(feature: str, name: str = "") -> str:
    return extract_feature_profile(feature, name).summary()
