"""知识库：导入即学习，写入标准项与成本记录。"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.db.database import get_connection
from src.ingest.parser import ParsedLine, ParsedWorkbook, parse_workbook
from src.normalize.feature_extract import extract_feature_profile
from src.normalize.text import (
    feature_fingerprint,
    normalize_feature,
    normalize_name,
    normalize_unit,
)


def _load_settings() -> dict:
    p = Path(__file__).resolve().parents[2] / "config" / "settings.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _median(vals: List[float]) -> float:
    vals = [v for v in vals if v is not None]
    if not vals:
        return 0.0
    return float(statistics.median(vals))


class KnowledgeRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.settings = _load_settings()

    def conn(self):
        return get_connection(self.db_path)

    def create_project(
        self,
        name: str,
        project_type: str,
        source_file: str,
        remark: str = "",
    ) -> int:
        conn = self.conn()
        try:
            cur = conn.execute(
                """INSERT INTO projects (name, project_type, source_file, remark)
                   VALUES (?, ?, ?, ?)""",
                (name, project_type, source_file, remark),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def get_or_create_standard_item(
        self,
        conn,
        list_code: str,
        name: str,
        feature: str,
        unit: str,
    ) -> int:
        nn = normalize_name(name)
        fn = normalize_feature(feature)
        un = normalize_unit(unit)
        fp = feature_fingerprint(fn)
        prof = extract_feature_profile(feature, name)
        msig = prof.signature()
        msum = prof.summary()
        tags_json = json.dumps(prof.tags, ensure_ascii=False)

        row = conn.execute(
            """SELECT id FROM standard_items
               WHERE name_norm=? AND unit_norm=? AND method_signature=?""",
            (nn, un, msig),
        ).fetchone()
        if row:
            conn.execute(
                """UPDATE standard_items SET feature_norm=?, feature_fingerprint=?,
                   feature_tags_json=?, method_summary=?, updated_at=datetime('now','localtime')
                   WHERE id=?""",
                (fn, fp, tags_json, msum, int(row["id"])),
            )
            return int(row["id"])
        cur = conn.execute(
            """INSERT INTO standard_items
               (list_code, name_norm, feature_norm, unit_norm, feature_fingerprint,
                method_signature, feature_tags_json, method_summary, sample_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (list_code or None, nn, fn, un, fp, msig, tags_json, msum),
        )
        return int(cur.lastrowid)

    def _bump_sample_count(self, conn, standard_item_id: int) -> None:
        conn.execute(
            """UPDATE standard_items SET sample_count = sample_count + 1,
               updated_at = datetime('now','localtime') WHERE id=?""",
            (standard_item_id,),
        )

    def insert_boq_line(self, conn, project_id: int, line: ParsedLine) -> int:
        nn = normalize_name(line.name)
        fn = normalize_feature(line.feature)
        un = normalize_unit(line.unit)
        prof = extract_feature_profile(line.feature, line.name)
        cur = conn.execute(
            """INSERT INTO boq_lines
               (project_id, sheet_name, section_path, seq, list_code, name, feature, unit,
                quantity, unit_price, amount, remark, name_norm, feature_norm, unit_norm,
                method_signature, method_summary, row_index)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                project_id,
                line.sheet_name,
                line.section_path,
                line.seq,
                line.list_code,
                line.name,
                line.feature,
                line.unit,
                line.quantity,
                line.unit_price,
                line.amount,
                line.remark,
                nn,
                fn,
                un,
                prof.signature(),
                prof.summary(),
                line.row_index,
            ),
        )
        return int(cur.lastrowid)

    def insert_cost_record(
        self,
        conn,
        standard_item_id: int,
        project_id: int,
        line_id: int,
        line: ParsedLine,
    ) -> int:
        cost = line.cost_unit_price
        if cost is None:
            parts = [
                line.material_main or 0,
                line.material_aux or 0,
                line.labor or 0,
                line.machinery or 0,
                line.management or 0,
                line.profit or 0,
            ]
            cost = sum(parts) if any(parts) else 0.0
        cur = conn.execute(
            """INSERT INTO cost_records
               (standard_item_id, source_project_id, source_line_id,
                material_main, material_aux, labor, machinery, management, profit,
                cost_unit_price, unit_price, is_verified)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""",
            (
                standard_item_id,
                project_id,
                line_id,
                line.material_main or 0,
                line.material_aux or 0,
                line.labor or 0,
                line.machinery or 0,
                line.management or 0,
                line.profit or 0,
                cost,
                line.unit_price,
            ),
        )
        self._bump_sample_count(conn, standard_item_id)
        return int(cur.lastrowid)

    def learn_from_file(
        self,
        file_path: str | Path,
        project_name: Optional[str] = None,
        project_type: str = "historical",
    ) -> Dict[str, Any]:
        """分析新清单+价格并写入知识库（您给新资料时调用）。"""
        wb = parse_workbook(file_path)
        name = project_name or wb.project_name
        conn = self.conn()
        learned = 0
        skipped = 0
        try:
            cur = conn.execute(
                """INSERT INTO projects (name, project_type, source_file, remark)
                   VALUES (?, ?, ?, ?)""",
                (name, project_type, wb.file_path, f"auto:{wb.format_hint}"),
            )
            pid = int(cur.lastrowid)

            for line in wb.lines:
                line_id = self.insert_boq_line(conn, pid, line)
                if line.has_cost_detail or line.cost_unit_price is not None:
                    sid = self.get_or_create_standard_item(
                        conn, line.list_code, line.name, line.feature, line.unit
                    )
                    self.insert_cost_record(conn, sid, pid, line_id, line)
                    learned += 1
                else:
                    skipped += 1
            conn.commit()
        finally:
            conn.close()

        return {
            "project_id": pid,
            "project_name": name,
            "total_lines": len(wb.lines),
            "learned_records": learned,
            "skipped_no_cost": skipped,
            "format": wb.format_hint,
        }

    def import_tender(self, file_path: str | Path, project_name: Optional[str] = None) -> Dict[str, Any]:
        """导入甲方招标清单（通常无成本明细）。"""
        wb = parse_workbook(file_path)
        name = project_name or wb.project_name
        conn = self.conn()
        try:
            cur = conn.execute(
                """INSERT INTO projects (name, project_type, source_file, remark)
                   VALUES (?, 'tender', ?, ?)""",
                (name, wb.file_path, "甲方招标清单"),
            )
            pid = int(cur.lastrowid)
            count = 0
            for line in wb.lines:
                self.insert_boq_line(conn, pid, line)
                count += 1
            conn.commit()
        finally:
            conn.close()
        return {"project_id": pid, "project_name": name, "line_count": count}

    def list_standard_items(self, limit: int = 20) -> List[dict]:
        conn = self.conn()
        try:
            rows = conn.execute(
                """SELECT id, name_norm, feature_norm, unit_norm, sample_count
                   FROM standard_items ORDER BY sample_count DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_cost_records_for_item(self, standard_item_id: int) -> List[dict]:
        conn = self.conn()
        try:
            rows = conn.execute(
                """SELECT * FROM cost_records WHERE standard_item_id=?""",
                (standard_item_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def aggregate_costs(self, records: List[dict]) -> Dict[str, float]:
        if not records:
            return {}
        mode = self.settings.get("pricing", {}).get("aggregate", "median")
        keys = [
            "material_main",
            "material_loss_rate",
            "material_aux",
            "labor",
            "machinery",
            "management",
            "profit",
            "cost_unit_price",
            "unit_price",
        ]
        out = {}
        for k in keys:
            vals = [float(r[k]) for r in records if r.get(k) is not None]
            if not vals:
                out[k] = 0.0
            elif mode == "mean":
                out[k] = sum(vals) / len(vals)
            else:
                out[k] = _median(vals)
        return out

    def stats(self) -> Dict[str, int]:
        conn = self.conn()
        try:
            p = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
            s = conn.execute("SELECT COUNT(*) c FROM standard_items").fetchone()["c"]
            r = conn.execute("SELECT COUNT(*) c FROM cost_records").fetchone()["c"]
            return {"projects": p, "standard_items": s, "cost_records": r}
        finally:
            conn.close()
