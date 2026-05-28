"""每次入库后的标准「解剖分析」：拆分人材机、归并相似项、更新城市×档位价库、导出报告。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.db.database import resolve_db_path
from src.ingest.parser import parse_workbook
from src.knowledge.craft_profiles import rebuild_craft_cost_profiles
from src.knowledge.facts import rebuild_material_price_facts
from src.knowledge.metadata import ProjectMetadata, infer_metadata
from src.normalize.feature_extract import extract_feature_profile


def run_post_learn_anatomy(
    conn,
    project_id: int,
    file_path: str | Path,
    meta: ProjectMetadata,
) -> Dict[str, Any]:
    """学习提交后：重建材料价库、统计本项目的知识贡献。"""
    mat_count = rebuild_material_price_facts(conn)
    craft_count = rebuild_craft_cost_profiles(conn)
    line_facts = conn.execute(
        """SELECT COUNT(*) c FROM line_price_facts lpf
           JOIN cost_records cr ON cr.standard_item_id = lpf.standard_item_id
           WHERE cr.source_project_id=?""",
        (project_id,),
    ).fetchone()["c"]

    distinct_items = conn.execute(
        """SELECT COUNT(DISTINCT standard_item_id) c FROM cost_records
           WHERE source_project_id=?""",
        (project_id,),
    ).fetchone()["c"]

    return {
        "city": meta.city,
        "price_tier": meta.price_tier,
        "scope_label": meta.label(),
        "material_price_facts_total": mat_count,
        "craft_cost_profiles_total": craft_count,
        "line_price_facts_touched": line_facts,
        "standard_items_contributed": distinct_items,
    }


def export_anatomy_report(
    project_id: int,
    file_path: str | Path,
    *,
    meta: Optional[ProjectMetadata] = None,
    db_path: Optional[str] = None,
    output_path: Optional[str | Path] = None,
) -> Path:
    """
    导出本项目解剖报告 Excel（每次给资料 learn 后自动生成）。
    """
    from src.db.database import get_connection

    fp = Path(file_path)
    meta = meta or infer_metadata(fp, "")
    conn = get_connection(db_path)
    try:
        proj = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not proj:
            raise ValueError(f"项目不存在: {project_id}")

        rows = conn.execute(
            """SELECT b.name, b.feature, b.unit, b.quantity,
                      cr.material_main, cr.material_loss_rate, cr.material_aux,
                      cr.labor, cr.machinery, cr.cost_unit_price,
                      si.method_summary, si.id AS std_id
               FROM boq_lines b
               LEFT JOIN cost_records cr ON cr.source_line_id = b.id
               LEFT JOIN standard_items si ON si.id = cr.standard_item_id
               WHERE b.project_id=?
               ORDER BY b.id""",
            (project_id,),
        ).fetchall()

        detail: List[dict] = []
        for r in rows:
            prof = extract_feature_profile(r["feature"] or "", r["name"] or "")
            qty = float(r["quantity"] or 0)
            cu = float(r["cost_unit_price"] or 0)
            detail.append(
                {
                    "项目名称": r["name"],
                    "做法摘要": r["method_summary"] or prof.summary(),
                    "项目特征": (r["feature"] or "")[:200],
                    "单位": r["unit"],
                    "工程量": qty,
                    "主材": r["material_main"],
                    "损耗率": r["material_loss_rate"],
                    "辅材": r["material_aux"],
                    "人工": r["labor"],
                    "机械": r["machinery"],
                    "成本单价": cu,
                    "成本合价": round(cu * qty, 2) if cu and qty else None,
                    "标准项ID": r["std_id"],
                }
            )

        df_detail = pd.DataFrame(detail)
        if not df_detail.empty and df_detail["标准项ID"].notna().any():
            agg = (
                df_detail.dropna(subset=["标准项ID"])
                .groupby(["项目名称", "单位", "做法摘要"], as_index=False)
                .agg(
                    样本数=("成本单价", "count"),
                    主材中位=("主材", "median"),
                    辅材中位=("辅材", "median"),
                    人工中位=("人工", "median"),
                    机械中位=("机械", "median"),
                    成本单价中位=("成本单价", "median"),
                )
            )
        else:
            agg = pd.DataFrame()

        city, tier = proj["city"] or meta.city, proj["price_tier"] or meta.price_tier
        mats = conn.execute(
            """SELECT material_key, spec_text, unit_norm, material_main, sample_count
               FROM material_price_facts
               WHERE city=? AND price_tier=?
               ORDER BY sample_count DESC LIMIT 200""",
            (city, tier),
        ).fetchall()
        df_mat = pd.DataFrame([dict(m) for m in mats]) if mats else pd.DataFrame()

        summary = pd.DataFrame(
            [
                {"项": "工程名称", "值": proj["name"]},
                {"项": "来源文件", "值": proj["source_file"]},
                {"项": "城市", "值": city or "通用"},
                {"项": "价格档位", "值": tier},
                {"项": "有成本行数", "值": len([d for d in detail if d["成本单价"]])},
                {"项": "材料价库(同城同档)", "值": len(df_mat)},
            ]
        )

        out_dir = resolve_db_path(db_path).parent / "exports" / "解剖报告"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in proj["name"])[:36]
        out = Path(output_path) if output_path else out_dir / f"解剖_{safe}_p{project_id}.xlsx"

        with pd.ExcelWriter(out, engine="openpyxl") as w:
            summary.to_excel(w, sheet_name="01_项目概要", index=False)
            df_detail.to_excel(w, sheet_name="02_清单人材机分解", index=False)
            if not agg.empty:
                agg.to_excel(w, sheet_name="03_相似项聚合", index=False)
            if not df_mat.empty:
                df_mat.to_excel(w, sheet_name="04_材料价库同城同档", index=False)
            pd.DataFrame(
                [
                    {"说明": "每次 learn 自动执行：识别表头→拆分主材/辅材/人工/机械→归并标准项"},
                    {"说明": "按城市×高/中/低档写入 line_price_facts、material_price_facts"},
                    {"说明": "招标组价时：名称+特征相似才整项参照，否则查同规格材料价"},
                ]
            ).to_excel(w, sheet_name="说明", index=False)

        return out
    finally:
        conn.close()
