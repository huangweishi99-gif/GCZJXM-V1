"""知识库事实表：按城市×档位聚合清单项单价与材料主材价。"""
from __future__ import annotations

import statistics
from typing import List, Optional

from src.normalize.material_spec import extract_material_spec


def _median(vals: List[float]) -> float:
    vals = [v for v in vals if v is not None and v > 0]
    if not vals:
        return 0.0
    return float(statistics.median(vals))


def rebuild_line_price_facts(conn, standard_item_id: Optional[int] = None) -> int:
    """从 cost_records 聚合 line_price_facts（清单项×城市×档位）。"""
    where = ""
    params: tuple = ()
    if standard_item_id is not None:
        where = " AND cr.standard_item_id=? "
        params = (standard_item_id,)

    rows = conn.execute(
        f"""SELECT cr.standard_item_id,
                   COALESCE(p.city, '') AS city,
                   COALESCE(p.price_tier, 'mid') AS price_tier,
                   cr.material_main, cr.material_loss_rate, cr.material_aux,
                   cr.labor, cr.machinery, cr.cost_unit_price
            FROM cost_records cr
            JOIN projects p ON p.id = cr.source_project_id
            WHERE 1=1 {where}""",
        params,
    ).fetchall()

    buckets: dict = {}
    for r in rows:
        key = (int(r["standard_item_id"]), r["city"] or "", r["price_tier"] or "mid")
        buckets.setdefault(key, []).append(dict(r))

    updated = 0
    for (sid, city, tier), recs in buckets.items():
        conn.execute(
            """INSERT INTO line_price_facts
               (standard_item_id, city, price_tier,
                material_main, material_loss_rate, material_aux, labor, machinery,
                cost_unit_price, sample_count, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?, datetime('now','localtime'))
               ON CONFLICT(standard_item_id, city, price_tier) DO UPDATE SET
                 material_main=excluded.material_main,
                 material_loss_rate=excluded.material_loss_rate,
                 material_aux=excluded.material_aux,
                 labor=excluded.labor,
                 machinery=excluded.machinery,
                 cost_unit_price=excluded.cost_unit_price,
                 sample_count=excluded.sample_count,
                 updated_at=datetime('now','localtime')""",
            (
                sid,
                city,
                tier,
                _median([x["material_main"] for x in recs]),
                _median([x["material_loss_rate"] for x in recs]),
                _median([x["material_aux"] for x in recs]),
                _median([x["labor"] for x in recs]),
                _median([x["machinery"] for x in recs]),
                _median([x["cost_unit_price"] for x in recs]),
                len(recs),
            ),
        )
        updated += 1
    return updated


def upsert_material_fact_from_line(
    conn,
    name: str,
    feature: str,
    unit: str,
    city: str,
    price_tier: str,
    material_main: float,
    material_loss_rate: float = 0.0,
) -> None:
    """单条成本入库时同步材料价库。"""
    spec = extract_material_spec(name, feature)
    if not spec or material_main <= 0:
        return
    key = spec.category
    if spec.size:
        key = f"{spec.category}:{spec.size}"
    spec_text = spec.size or ""
    from src.normalize.text import normalize_unit

    un = normalize_unit(unit)
    c = city or ""
    t = price_tier or "mid"

    conn.execute(
        """INSERT INTO material_price_facts
           (material_key, material_category, spec_text, unit_norm, city, price_tier,
            material_main, material_loss_rate, sample_count)
           VALUES (?,?,?,?,?,?,?,?,1)
           ON CONFLICT(material_key, unit_norm, city, price_tier) DO UPDATE SET
             material_main = (material_main * sample_count + excluded.material_main)
                             / (sample_count + 1),
             material_loss_rate = excluded.material_loss_rate,
             sample_count = sample_count + 1,
             updated_at = datetime('now','localtime')""",
        (key, spec.category, spec_text, un, c, t, material_main, material_loss_rate),
    )


def rebuild_material_price_facts(conn) -> int:
    """全量从 cost_records 重建材料价库。"""
    conn.execute("DELETE FROM material_price_facts")
    rows = conn.execute(
        """SELECT cr.material_main, cr.material_loss_rate,
                  si.name_norm, si.feature_norm, si.unit_norm,
                  COALESCE(p.city,'') city, COALESCE(p.price_tier,'mid') price_tier
           FROM cost_records cr
           JOIN standard_items si ON si.id = cr.standard_item_id
           JOIN projects p ON p.id = cr.source_project_id
           WHERE cr.material_main > 0"""
    ).fetchall()
    for r in rows:
        upsert_material_fact_from_line(
            conn,
            r["name_norm"],
            r["feature_norm"] or "",
            r["unit_norm"],
            r["city"],
            r["price_tier"],
            float(r["material_main"]),
            float(r["material_loss_rate"] or 0),
        )
    return conn.execute("SELECT COUNT(*) c FROM material_price_facts").fetchone()["c"]
