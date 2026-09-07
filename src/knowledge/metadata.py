"""从工程名、路径推断城市与价格档位（高/中/低）。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    """显式参数优先；未显式指定的维度各自回退到文件名/工程名推断。"""
    if city is not None and price_tier is not None:
        return ProjectMetadata(
            city=normalize_city(city),
            price_tier=normalize_tier(price_tier),
        )

    cfg = _load_regions()
    text = f"{project_name} {Path(file_path).name} {file_path}"

    if city is None:
        city = ""
        for city_name, kws in cfg.get("path_keywords", {}).items():
            if any(kw in text for kw in kws):
                city = city_name
                break
    if price_tier is None:
        price_tier = cfg.get("default_tier", "mid")
        for tier, kws in cfg.get("tier_keywords", {}).items():
            if any(kw in text for kw in kws):
                price_tier = tier
                break

    return ProjectMetadata(city=normalize_city(city), price_tier=normalize_tier(price_tier))


def pair_meta_by_source() -> Dict[str, Dict[str, Any]]:
    """project_pairs 登记的项目元数据，按源文件归一化路径索引。

    覆盖 pairs 中出现的全部清单路径（gold / tender / tender_fallback /
    tenders / reference_tenders），用于：
      - 定稿标记：is_gold 决定该源文件的样本是否为「已闭环定稿」；
      - 城市回填：文件名关键字推断不出城市时，采用人工登记的城市，
        避免定稿样本落入「通用桶」、以某地价格污染其它城市报价。

    同一路径被多个 pair 引用时（如既是 A 的定稿又是 B 的参考清单），
    is_gold 取「或」，城市/档位保留首次登记值。
    """
    root = Path(__file__).resolve().parents[2]
    cfg = root / "config" / "project_pairs.json"
    out: Dict[str, Dict[str, Any]] = {}
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        return out

    def _paths(it: Dict[str, Any], keys: List[str]) -> List[str]:
        vals: List[str] = []
        for k in keys:
            v = it.get(k)
            if isinstance(v, str) and v:
                vals.append(v)
            elif isinstance(v, list):
                vals.extend([str(x) for x in v if x])
        return vals

    for it in data.get("pairs") or []:
        rec = {
            "pair_id": str(it.get("id") or ""),
            "city": str(it.get("city") or "").strip(),
            "tier": str(it.get("tier") or "").strip(),
            "label": str(it.get("label") or ""),
        }
        groups = (
            ("gold", _paths(it, ["gold"]), True),
            ("tender", _paths(it, ["tender", "tender_fallback", "tenders"]), False),
            ("reference", _paths(it, ["reference_tenders"]), False),
        )
        for role, paths, is_gold in groups:
            for p in paths:
                try:
                    key = os.path.normcase(str((root / p).resolve()))
                except Exception:
                    continue
                hit = out.get(key)
                if hit is None:
                    item = dict(rec)
                    item["role"] = role
                    item["is_gold"] = bool(is_gold)
                    out[key] = item
                else:
                    # 同一文件被多个 pair 引用：定稿资格取「或」，城市保留首个非空登记
                    hit["is_gold"] = bool(hit.get("is_gold")) or bool(is_gold)
                    if not hit.get("city"):
                        hit["city"] = rec["city"]
    return out
