# -*- coding: utf-8 -*-
"""项目主材编号价表（如售楼处主材料.xlsx）导入与查询。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

import openpyxl

from src.db.database import get_connection
from src.knowledge.facts import upsert_material_fact_from_line
from src.normalize.text import normalize_name, normalize_unit

MATERIAL_CODE_RE = re.compile(
    r"([A-Z]{2}-\d{1,2}(?:\.\d{1,2})?[a-zA-Z]?)(?![A-Z0-9.\-])",
    re.I,
)

_CODE_CATEGORY = {
    "PT": "涂料",
    "GL": "玻璃",
    "MT": "金属",
    "AL": "金属",
    "CA": "地毯",
    "UP": "布艺皮革",
    "ST": "石材",
    "CT": "瓷砖",
    "CP": "毛毡",
    "WD": "木作",
    "SP": "其他饰面",
    "SF": "软装",
    "MR": "镜子",
    "DF": "其他饰面",
}


def extract_material_codes(name: str, feature: str = "") -> List[str]:
    """从名称+特征提取物料编号（PT-01、CT-01.02、ST-04a 等），去重保序（长编号优先）。"""
    text = f"{name or ''} {feature or ''}"
    seen: set[str] = set()
    raw: List[str] = []
    for m in MATERIAL_CODE_RE.finditer(text):
        code = m.group(1).upper()
        if code not in seen:
            seen.add(code)
            raw.append(code)
    raw.sort(key=lambda c: (-len(c), text.upper().find(c)))
    return raw


def _category_from_code(code: str) -> str:
    prefix = code.split("-")[0].upper()
    return _CODE_CATEGORY.get(prefix, "饰面")


def import_project_materials_xlsx(
    file_path: str | Path,
    *,
    project_name: str,
    project_ref: str,
    city: str = "",
    price_tier: str = "mid",
    db_path: Optional[str] = None,
) -> dict:
    """
    导入项目主材表（物料编号、名称、单位、不含税主材价）。
    写入 project_material_prices，并同步 material_price_facts（key=code:PT-01）。
    """
    fp = Path(file_path)
    wb = openpyxl.load_workbook(fp, data_only=True)
    ws = wb.active
    rows_in: list = []
    section = ""

    for r in range(1, ws.max_row + 1):
        code = ws.cell(r, 1).value
        name = ws.cell(r, 2).value
        spec = ws.cell(r, 3).value
        area = ws.cell(r, 4).value
        unit = ws.cell(r, 6).value
        price = ws.cell(r, 7).value
        remark = ws.cell(r, 8).value

        if code and isinstance(code, str) and not re.match(r"^[A-Z]{2}-\d", code.strip(), re.I):
            if name and str(name).strip() and not price:
                section = str(name).strip()
            continue

        if not code or not isinstance(code, str):
            continue
        code = code.strip().upper()
        if not re.match(r"^[A-Z]{2}-\d", code):
            continue
        if price is None:
            continue
        try:
            price_f = float(price)
        except (TypeError, ValueError):
            continue
        if price_f <= 0:
            continue

        mat_name = str(name).strip() if name else code
        un = normalize_unit(str(unit) if unit else "㎡")
        rows_in.append(
            {
                "material_code": code,
                "material_name": mat_name,
                "name_norm": normalize_name(mat_name),
                "spec_text": str(spec).strip() if spec else "",
                "use_area": str(area).strip() if area else "",
                "unit_norm": un,
                "material_main": price_f,
                "category": section or _category_from_code(code),
                "remark": str(remark).strip() if remark else "",
            }
        )

    conn = get_connection(db_path)
    try:
        conn.execute(
            "DELETE FROM project_material_prices WHERE project_ref=? AND source_file=?",
            (project_ref, str(fp)),
        )
        for row in rows_in:
            conn.execute(
                """INSERT OR REPLACE INTO project_material_prices
                   (material_code, material_name, name_norm, spec_text, use_area,
                    unit_norm, material_main, category, project_name, project_ref,
                    city, price_tier, source_file, remark)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["material_code"],
                    row["material_name"],
                    row["name_norm"],
                    row["spec_text"],
                    row["use_area"],
                    row["unit_norm"],
                    row["material_main"],
                    row["category"],
                    project_name,
                    project_ref,
                    city or "",
                    price_tier or "mid",
                    str(fp),
                    row["remark"],
                ),
            )
            conn.execute(
                """INSERT INTO material_price_facts
                   (material_key, material_category, spec_text, unit_norm, city, price_tier,
                    material_main, material_loss_rate, sample_count)
                   VALUES (?,?,?,?,?,?,?,?,1)
                   ON CONFLICT(material_key, unit_norm, city, price_tier) DO UPDATE SET
                     material_main=excluded.material_main,
                     sample_count=sample_count+1,
                     updated_at=datetime('now','localtime')""",
                (
                    f"code:{row['material_code']}",
                    row["category"],
                    row["material_code"],
                    row["unit_norm"],
                    city or "",
                    price_tier or "mid",
                    row["material_main"],
                    0.0,
                ),
            )
            upsert_material_fact_from_line(
                conn,
                f"{row['material_code']} {row['material_name']}",
                row["spec_text"],
                row["unit_norm"],
                city or "",
                price_tier or "mid",
                row["material_main"],
                0.0,
            )
        conn.commit()
        total = conn.execute(
            "SELECT COUNT(*) c FROM project_material_prices WHERE project_ref=?",
            (project_ref,),
        ).fetchone()["c"]
    finally:
        conn.close()

    return {
        "imported": len(rows_in),
        "project_ref": project_ref,
        "project_name": project_name,
        "city": city,
        "price_tier": price_tier,
        "catalog_total": total,
        "source": str(fp),
        "codes": [r["material_code"] for r in rows_in],
    }


def lookup_project_material_row(
    name: str,
    feature: str,
    unit: str,
    *,
    city: str = "",
    price_tier: str = "mid",
    project_ref: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Tuple[Optional[dict], str]:
    """
    按清单名称/特征中的物料编号查项目主材价。
    返回 (row_dict, note) 或 (None, "")。
    """
    codes = extract_material_codes(name, feature)
    if not codes:
        return None, ""

    un = normalize_unit(unit)
    conn = get_connection(db_path)
    try:
        for code in codes:
            try_codes = [code]
            if code.upper() == "WD-03":
                try_codes.append("WD-04")
            for tc in try_codes:
                queries = []
                params: list = []
                if project_ref:
                    queries.append(
                        """SELECT * FROM project_material_prices
                           WHERE material_code=? AND project_ref=?
                             AND (unit_norm=? OR unit_norm='' OR ?='')"""
                    )
                    params.append((tc, project_ref, un, un))
                for city_try in ([city, ""] if city else [""]):
                    for tier_try in ([price_tier, "mid"] if price_tier else ["mid"]):
                        queries.append(
                            """SELECT * FROM project_material_prices
                               WHERE material_code=? AND city=? AND price_tier=?
                                 AND (unit_norm=? OR unit_norm='' OR ?='')
                               ORDER BY project_ref DESC LIMIT 1"""
                        )
                        params.append((tc, city_try, tier_try, un, un))

                row = None
                for sql, p in zip(queries, params):
                    row = conn.execute(sql, p).fetchone()
                    if row:
                        break
                if not row:
                    continue
                note = (
                    f"[项目主材表]{row['project_name']}·{tc}·{row['material_name']}"
                    f" 主材{float(row['material_main']):.2f}/{row['unit_norm']}"
                )
                if tc != code:
                    note = f"{note}（{code}→{tc}）"
                return dict(row), note
    finally:
        conn.close()
    return None, ""
