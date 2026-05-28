"""从工程名、路径推断城市与价格档位（高/中/低）。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

_VALID_TIERS = frozenset({"high", "mid", "low"})


@dataclass
class ProjectMetadata:
    city: str = ""
    price_tier: str = "mid"

    def label(self) -> str:
        parts = []
        if self.city:
            parts.append(self.city)
        tier_map = _load_regions().get("tiers", {})
        parts.append(tier_map.get(self.price_tier, self.price_tier))
        return "·".join(parts) if parts else "默认"


def _load_regions() -> dict:
    p = Path(__file__).resolve().parents[2] / "config" / "regions.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"default_city": "", "default_tier": "mid", "path_keywords": {}, "tier_keywords": {}}


def normalize_tier(tier: Optional[str]) -> str:
    if not tier:
        cfg = _load_regions()
        return cfg.get("default_tier", "mid")
    t = str(tier).strip().lower()
    alias = {"高": "high", "高档": "high", "中": "mid", "中档": "mid", "低": "low", "低档": "low"}
    t = alias.get(t, t)
    return t if t in _VALID_TIERS else _load_regions().get("default_tier", "mid")


def normalize_city(city: Optional[str]) -> str:
    if not city:
        return _load_regions().get("default_city", "")
    c = str(city).strip()
    if c in ("全国", "通用", "默认"):
        return ""
    return c


def infer_metadata(
    file_path: str | Path = "",
    project_name: str = "",
    *,
    city: Optional[str] = None,
    price_tier: Optional[str] = None,
) -> ProjectMetadata:
    """显式参数优先，否则从文件名/工程名推断。"""
    if city is not None or price_tier is not None:
        return ProjectMetadata(
            city=normalize_city(city),
            price_tier=normalize_tier(price_tier),
        )

    cfg = _load_regions()
    text = f"{project_name} {Path(file_path).name} {file_path}"
    found_city = ""
    for city_name, kws in cfg.get("path_keywords", {}).items():
        if any(kw in text for kw in kws):
            found_city = city_name
            break

    found_tier = cfg.get("default_tier", "mid")
    for tier, kws in cfg.get("tier_keywords", {}).items():
        if any(kw in text for kw in kws):
            found_tier = tier
            break

    return ProjectMetadata(city=found_city, price_tier=normalize_tier(found_tier))
