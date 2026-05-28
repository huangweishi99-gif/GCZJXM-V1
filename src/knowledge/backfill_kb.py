"""回填历史项目的城市/档位，并重建价库事实表。"""
from __future__ import annotations

from typing import Any, Dict

from src.knowledge.craft_profiles import rebuild_craft_cost_profiles
from src.knowledge.facts import rebuild_line_price_facts, rebuild_material_price_facts
from src.knowledge.metadata import infer_metadata


def backfill_projects_and_facts(conn) -> Dict[str, Any]:
    rows = conn.execute(
        "SELECT id, name, source_file, city, price_tier FROM projects"
    ).fetchall()
    updated_meta = 0
    for r in rows:
        meta = infer_metadata(r["source_file"] or "", r["name"] or "")
        if (not r["city"] and meta.city) or (r["price_tier"] in (None, "", "mid") and meta.price_tier != "mid"):
            conn.execute(
                "UPDATE projects SET city=?, price_tier=?, region=? WHERE id=?",
                (meta.city, meta.price_tier, meta.city, int(r["id"])),
            )
            updated_meta += 1

    line_n = rebuild_line_price_facts(conn)
    mat_n = rebuild_material_price_facts(conn)
    craft_n = rebuild_craft_cost_profiles(conn)
    return {
        "projects_meta_updated": updated_meta,
        "line_price_facts": line_n,
        "material_price_facts": mat_n,
        "craft_cost_profiles": craft_n,
    }
