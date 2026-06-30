"""回填历史 cost_records：整价无分项时按工艺份额拆分。"""
from __future__ import annotations

from typing import Any, Dict

from src.knowledge.facts import rebuild_line_price_facts
from src.knowledge.craft_profiles import rebuild_craft_cost_profiles
from src.knowledge.cost_split import needs_component_split, split_whole_price_components


def backfill_cost_component_splits(conn) -> Dict[str, Any]:
    rows = conn.execute(
        """SELECT cr.id, cr.cost_unit_price, cr.material_main, cr.material_aux,
                  cr.labor, cr.machinery, cr.standard_item_id,
                  COALESCE(bl.name, si.name_norm) AS name,
                  COALESCE(bl.feature, '') AS feature,
                  COALESCE(bl.unit, si.unit_norm) AS unit
           FROM cost_records cr
           JOIN standard_items si ON si.id = cr.standard_item_id
           LEFT JOIN boq_lines bl ON bl.id = cr.source_line_id
           WHERE cr.cost_unit_price >= 1"""
    ).fetchall()

    updated = 0
    touched_items: set[int] = set()
    for r in rows:
        cost = float(r["cost_unit_price"] or 0)
        if not needs_component_split(
            cost,
            float(r["material_main"] or 0),
            float(r["material_aux"] or 0),
            float(r["labor"] or 0),
            float(r["machinery"] or 0),
        ):
            continue
        comps = split_whole_price_components(
            r["name"] or "",
            r["feature"] or "",
            r["unit"] or "",
            cost,
        )
        conn.execute(
            """UPDATE cost_records SET
               material_main=?, material_aux=?, labor=?, machinery=?,
               material_loss_rate=?
               WHERE id=?""",
            (
                comps["material_main"],
                comps["material_aux"],
                comps["labor"],
                comps["machinery"],
                comps.get("material_loss_rate", 0),
                int(r["id"]),
            ),
        )
        updated += 1
        touched_items.add(int(r["standard_item_id"]))

    for sid in touched_items:
        rebuild_line_price_facts(conn, sid)

    craft_n = rebuild_craft_cost_profiles(conn)

    return {
        "records_scanned": len(rows),
        "records_updated": updated,
        "standard_items_touched": len(touched_items),
        "craft_profiles_rebuilt": craft_n,
    }
