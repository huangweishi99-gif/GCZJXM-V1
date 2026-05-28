"""主材/辅材判定目录：导入与查询。"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from src.db.database import get_connection
from src.normalize.text import normalize_name

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
}


def _category_from_code(code: Optional[str]) -> Optional[str]:
    if not code or not isinstance(code, str):
        return None
    prefix = code.split("-")[0].upper()
    return _CODE_CATEGORY.get(prefix)


def import_material_catalog_xlsx(
    file_path: str | Path,
    db_path: Optional[str] = None,
) -> dict:
    """导入 主材辅材判定.xlsx 到 material_catalog 表。"""
    fp = Path(file_path)
    raw = pd.read_excel(fp, sheet_name=0, header=None)
    section = ""
    rows_data = []
    for i in range(2, len(raw)):
        r = raw.iloc[i]
        if pd.isna(r[3]) and pd.notna(r[1]) and str(r[1]) not in ("装饰", "安装", "空调"):
            section = str(r[1]).strip()
            continue
        if pd.isna(r[3]):
            continue
        role = str(r[5]).strip() if pd.notna(r[5]) else ""
        if role not in ("主材", "辅材"):
            continue
        code = str(r[2]).strip() if pd.notna(r[2]) else None
        rows_data.append(
            {
                "trade": str(r[1]) if pd.notna(r[1]) else None,
                "code": code,
                "name": str(r[3]).strip(),
                "brands": str(r[4]) if pd.notna(r[4]) else None,
                "role": role,
                "category": section or _category_from_code(code),
            }
        )

    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM material_catalog WHERE source_file=?", (str(fp),))
        for row in rows_data:
            conn.execute(
                """INSERT INTO material_catalog
                   (material_code, material_name, name_norm, category, trade, role, brands, source_file)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    row["code"],
                    row["name"],
                    normalize_name(row["name"]),
                    row["category"],
                    row["trade"],
                    row["role"],
                    row["brands"],
                    str(fp),
                ),
            )
        conn.commit()
        total = conn.execute("SELECT COUNT(*) c FROM material_catalog").fetchone()["c"]
        main_c = conn.execute(
            "SELECT COUNT(*) c FROM material_catalog WHERE role='主材'"
        ).fetchone()["c"]
        aux_c = conn.execute(
            "SELECT COUNT(*) c FROM material_catalog WHERE role='辅材'"
        ).fetchone()["c"]
    finally:
        conn.close()
    return {
        "imported": len(rows_data),
        "catalog_total": total,
        "main_count": main_c,
        "aux_count": aux_c,
        "source": str(fp),
    }


def classify_material_role(name: str, feature: str = "") -> Tuple[Optional[str], str]:
    """按目录判定主材/辅材。返回 (主材/辅材/None, 说明)"""
    text = normalize_name(name) + normalize_name(feature)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT material_name, name_norm, role FROM material_catalog ORDER BY length(name_norm) DESC"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return None, "未导入材料目录"

    for r in rows:
        nn = r["name_norm"] or ""
        if nn and (nn in text or nn in normalize_name(name)):
            return r["role"], f"材料目录：{r['material_name']}→{r['role']}"
    return None, "材料目录未命中"


def list_aux_material_names(db_path: Optional[str] = None) -> List[str]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT material_name FROM material_catalog WHERE role='辅材'"
        ).fetchall()
        return [r["material_name"] for r in rows]
    finally:
        conn.close()
