"""从名称/特征识别材料品类与规格（供知识库、组价共用）。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from src.normalize.text import normalize_name


@dataclass
class MaterialSpec:
    category: str
    size: Optional[str] = None
    thickness_mm: Optional[str] = None
    keywords: List[str] = field(default_factory=list)


def _load_rules() -> dict:
    p = Path(__file__).resolve().parents[2] / "config" / "material_rules.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _norm_size(w: str, h: str) -> str:
    return f"{int(w)}*{int(h)}"


def extract_material_spec(name: str, feature: str = "") -> Optional[MaterialSpec]:
    rules = _load_rules()
    combined = normalize_name(name) + "\n" + (feature or "")
    text_lower = combined.lower()

    cat_id = None
    kws: List[str] = []
    for cat in rules.get("categories", []):
        for kw in cat["keywords"]:
            if kw.lower() in text_lower or kw in combined:
                cat_id = cat["id"]
                kws.append(kw)
                break
        if cat_id:
            break
    if not cat_id:
        return None

    size = None
    sp = rules.get("size_pattern", r"(\d{2,4})\s*[*×xX]\s*(\d{2,4})")
    for m in re.finditer(sp, combined, re.I):
        size = _norm_size(m.group(1), m.group(2))
        break

    thk = None
    tp = rules.get("thickness_pattern")
    if tp:
        tm = re.search(tp, combined, re.I)
        if tm:
            thk = tm.group(1)

    return MaterialSpec(category=cat_id, size=size, thickness_mm=thk, keywords=kws)
