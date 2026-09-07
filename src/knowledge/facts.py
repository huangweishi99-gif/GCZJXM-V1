"""知识库事实表：按城市×档位聚合清单项单价与材料主材价。"""
from __future__ import annotations

import statistics
from typing import List, Optional

from src.normalize.material_spec import MaterialSpec, extract_material_spec

# 辅料类精确词表（胶水/剂类辅料，不应进主材价库）
_AUX_MATERIAL_WORDS = (
    "玻璃胶", "云石胶", "结构胶", "耐候胶", "密封胶", "硅酮胶", "中性胶",
    "白乳胶", "AB胶", "免钉胶", "瓷砖胶", "美缝剂", "勾缝剂", "填缝剂",
    "嵌缝剂", "界面剂", "防护剂", "固化剂", "稀释剂", "脱模剂", "防潮剂",
    "除锈剂", "堵漏剂", "粘结剂", "粘接剂", "密封剂", "防霉剂",
)
# 无材料单价意义的整项单位
_NO_MAIN_UNITS = {"项", "系统", "宗"}


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
                   cr.labor, cr.machinery, cr.cost_unit_price,
                   COALESCE(cr.is_verified, 0) AS is_verified
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
        # 定稿优先：同一清单项若存在已闭环定稿样本，只用定稿样本聚合，
        # 避免过程稿/旧版价混入中位数把定稿口径拉偏。
        verified = [x for x in recs if x["is_verified"]]
        recs = verified or recs
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
    only_if_absent: bool = False,
) -> None:
    """单条成本入库时同步材料价库。

    only_if_absent=True 时，若该材料价键已存在（通常已由定稿样本写入）则跳过，
    用于非定稿样本补齐定稿未覆盖的键。
    """
    from src.normalize.text import normalize_unit

    un = normalize_unit(unit)
    # 辅料（胶水/剂类）与整项单位不进主材价库，避免污染材料规格价
    if un in _NO_MAIN_UNITS:
        return
    if any(w in name for w in _AUX_MATERIAL_WORDS) or any(
        w in (feature or "") for w in _AUX_MATERIAL_WORDS
    ):
        return
    # 材料品类只看名称判定（特征里的"地面石材、砖"等描述词会带偏水泥/胶泥等）
    cat_spec = extract_material_spec(name, "")
    if not cat_spec or material_main <= 0:
        return
    # 规格可取自名称+特征，但品类始终保持名称判定结果
    size_spec = extract_material_spec(name, feature or "")
    spec = cat_spec
    if size_spec is not None and size_spec.size:
        spec = MaterialSpec(
            category=cat_spec.category,
            size=size_spec.size,
            thickness_mm=size_spec.thickness_mm,
            keywords=size_spec.keywords,
        )
    key = spec.category
    if spec.size:
        key = f"{spec.category}:{spec.size}"
    spec_text = spec.size or ""
    c = city or ""
    t = price_tier or "mid"

    if only_if_absent:
        exists = conn.execute(
            """SELECT 1 FROM material_price_facts
               WHERE material_key=? AND unit_norm=? AND city=? AND price_tier=?""",
            (key, un, c, t),
        ).fetchone()
        if exists:
            return

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
    """全量从 cost_records 重建材料价库（定稿样本优先，非定稿只补空缺键）。"""
    conn.execute("DELETE FROM material_price_facts")
    rows = conn.execute(
        """SELECT cr.material_main, cr.material_loss_rate,
                  si.name_norm, si.feature_norm, si.unit_norm,
                  COALESCE(p.city,'') city, COALESCE(p.price_tier,'mid') price_tier,
                  COALESCE(cr.is_verified, 0) AS is_verified
           FROM cost_records cr
           JOIN standard_items si ON si.id = cr.standard_item_id
           JOIN projects p ON p.id = cr.source_project_id
           WHERE cr.material_main > 0"""
    ).fetchall()
    # 第一遍：定稿样本
    for r in rows:
        if not r["is_verified"]:
            continue
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
    # 第二遍：非定稿样本只补齐定稿未覆盖的键
    for r in rows:
        if r["is_verified"]:
            continue
        upsert_material_fact_from_line(
            conn,
            r["name_norm"],
            r["feature_norm"] or "",
            r["unit_norm"],
            r["city"],
            r["price_tier"],
            float(r["material_main"]),
            float(r["material_loss_rate"] or 0),
            only_if_absent=True,
        )
    return conn.execute("SELECT COUNT(*) c FROM material_price_facts").fetchone()["c"]
