"""为已有标准项回填做法标签（method_signature）。"""
from __future__ import annotations

import json

from src.db.database import get_connection
from src.normalize.feature_extract import extract_feature_profile


def backfill_method_signatures(db_path=None) -> dict:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, name_norm, feature_norm FROM standard_items"
        ).fetchall()
        updated = 0
        for r in rows:
            prof = extract_feature_profile(r["feature_norm"] or "", r["name_norm"] or "")
            conn.execute(
                """UPDATE standard_items SET method_signature=?,
                   feature_tags_json=?, method_summary=? WHERE id=?""",
                (
                    prof.signature(),
                    json.dumps(prof.tags, ensure_ascii=False),
                    prof.summary(),
                    r["id"],
                ),
            )
            updated += 1
        conn.commit()
        return {"updated": updated}
    finally:
        conn.close()
