"""回填历史项目的城市/档位，并重建价库事实表。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from src.knowledge.craft_profiles import rebuild_craft_cost_profiles
from src.knowledge.facts import rebuild_line_price_facts, rebuild_material_price_facts
from src.knowledge.metadata import infer_metadata, pair_meta_by_source


def backfill_projects_and_facts(conn) -> Dict[str, Any]:
    rows = conn.execute(
        "SELECT id, name, source_file, city, price_tier FROM projects"
    ).fetchall()
    pairs = pair_meta_by_source()
    updated_meta = 0
    for r in rows:
        meta = infer_metadata(r["source_file"] or "", r["name"] or "")
        city = meta.city
        if not city and r["source_file"]:
            # 文件名关键字推断不出城市时，采用 project_pairs 人工登记的城市
            try:
                rec = pairs.get(os.path.normcase(str(Path(r["source_file"]).resolve())))
            except Exception:
                rec = None
            if rec and rec.get("city"):
                city = str(rec["city"])
        if (not r["city"] and city) or (r["price_tier"] in (None, "", "mid") and meta.price_tier != "mid"):
            conn.execute(
                "UPDATE projects SET city=?, price_tier=?, region=? WHERE id=?",
                (city, meta.price_tier, city, int(r["id"])),
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
