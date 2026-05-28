"""按城市、档位查询知识库（清单项单价 / 材料价），支持逐级放宽。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.knowledge.metadata import ProjectMetadata


@dataclass
class PricingContext:
    city: str = ""
    price_tier: str = "mid"

    @classmethod
    def from_metadata(cls, meta: ProjectMetadata) -> "PricingContext":
        return cls(city=meta.city, price_tier=meta.price_tier)

    def scope_note(self) -> str:
        parts = []
        if self.city:
            parts.append(self.city)
        parts.append({"high": "高档", "mid": "中档", "low": "低档"}.get(self.price_tier, self.price_tier))
        return "·".join(parts)


def _tier_fallback_order(tier: str) -> List[str]:
    order = {"high": ["high", "mid", "low"], "mid": ["mid", "high", "low"], "low": ["low", "mid", "high"]}
    return order.get(tier, ["mid", "high", "low"])


def _city_fallback_order(city: str) -> List[str]:
    if not city:
        return [""]
    return [city, ""]


def query_line_price_fact(
    conn,
    standard_item_id: int,
    ctx: PricingContext,
) -> Tuple[Optional[dict], str]:
    """查清单项聚合价：先同城同档，再放宽城市/档位。"""
    for city in _city_fallback_order(ctx.city):
        for tier in _tier_fallback_order(ctx.price_tier):
            row = conn.execute(
                """SELECT * FROM line_price_facts
                   WHERE standard_item_id=? AND city=? AND price_tier=?""",
                (standard_item_id, city, tier),
            ).fetchone()
            if row and row["sample_count"] > 0:
                note = f"知识库清单价({city or '通用'}·{tier}·{row['sample_count']}样本)"
                if city != ctx.city or tier != ctx.price_tier:
                    note += "【跨区/跨档参考】"
                return dict(row), note
    return None, ""


def query_material_price_fact(
    conn,
    material_key: str,
    unit_norm: str,
    ctx: PricingContext,
) -> Tuple[Optional[dict], str]:
    for city in _city_fallback_order(ctx.city):
        for tier in _tier_fallback_order(ctx.price_tier):
            row = conn.execute(
                """SELECT * FROM material_price_facts
                   WHERE material_key=? AND unit_norm=? AND city=? AND price_tier=?""",
                (material_key, unit_norm, city, tier),
            ).fetchone()
            if row and row["sample_count"] > 0:
                note = f"材料价库({material_key}·{city or '通用'}·{tier})"
                if city != ctx.city or tier != ctx.price_tier:
                    note += "【跨区/跨档】"
                return dict(row), note
    return None, ""


def filter_cost_records(
    records: List[dict],
    ctx: PricingContext,
) -> Tuple[List[dict], str]:
    """按城市/档位筛选 cost_records，逐步放宽。"""
    if not records:
        return [], ""

    def match(rec, city: str, tier: str) -> bool:
        rc = rec.get("city") or ""
        rt = rec.get("price_tier") or "mid"
        ok_city = (not city) or (rc == city) or (not rc)
        ok_tier = (not tier) or (rt == tier)
        return ok_city and ok_tier

    for city in _city_fallback_order(ctx.city):
        for tier in _tier_fallback_order(ctx.price_tier):
            subset = [r for r in records if match(r, city, tier)]
            if subset:
                note = ""
                if city != ctx.city or tier != ctx.price_tier:
                    note = "【跨区/跨档样本】"
                return subset, note
    return records, ""
