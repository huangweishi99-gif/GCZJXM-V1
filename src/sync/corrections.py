# -*- coding: utf-8 -*-
"""手机端提交的清单校正（按 dedupe_key + 特征 + 单位）。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.db.database import get_connection

ROOT = Path(__file__).resolve().parents[2]


def ensure_sync_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sync_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            revision INTEGER NOT NULL DEFAULT 0,
            bundle_path TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        INSERT OR IGNORE INTO sync_meta (id, revision) VALUES (1, 0);

        CREATE TABLE IF NOT EXISTS mobile_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            dedupe_key TEXT NOT NULL,
            name TEXT NOT NULL,
            feature TEXT NOT NULL DEFAULT '',
            unit TEXT NOT NULL,
            quantity REAL,
            material_main REAL,
            material_loss_rate REAL DEFAULT 0,
            material_aux REAL,
            labor REAL,
            machinery REAL,
            cost_unit_price REAL,
            note TEXT,
            device_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            synced_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mobile_corr_project
            ON mobile_corrections(project_id, status);
        """
    )


def get_revision(db_path: Optional[str | Path] = None) -> int:
    conn = get_connection(db_path)
    try:
        ensure_sync_tables(conn)
        row = conn.execute("SELECT revision FROM sync_meta WHERE id=1").fetchone()
        return int(row["revision"] if row else 0)
    finally:
        conn.close()


def bump_revision(db_path: Optional[str | Path] = None) -> int:
    conn = get_connection(db_path)
    try:
        ensure_sync_tables(conn)
        conn.execute(
            "UPDATE sync_meta SET revision = revision + 1, updated_at=datetime('now','localtime') WHERE id=1"
        )
        conn.commit()
        return get_revision(db_path)
    finally:
        conn.close()


def save_correction(payload: Dict[str, Any], db_path: Optional[str | Path] = None) -> int:
    conn = get_connection(db_path)
    try:
        ensure_sync_tables(conn)
        cur = conn.execute(
            """INSERT INTO mobile_corrections (
                project_id, dedupe_key, name, feature, unit, quantity,
                material_main, material_loss_rate, material_aux, labor, machinery,
                cost_unit_price, note, device_id, status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending')""",
            (
                payload["project_id"],
                payload["dedupe_key"],
                payload["name"],
                payload.get("feature") or "",
                payload["unit"],
                payload.get("quantity"),
                payload.get("material_main"),
                payload.get("material_loss_rate") or 0,
                payload.get("material_aux"),
                payload.get("labor"),
                payload.get("machinery"),
                payload.get("cost_unit_price"),
                payload.get("note"),
                payload.get("device_id"),
            ),
        )
        conn.commit()
        bump_revision(db_path)
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_corrections(
    *,
    project_id: Optional[str] = None,
    status: str = "pending",
    db_path: Optional[str | Path] = None,
) -> List[dict]:
    conn = get_connection(db_path)
    try:
        ensure_sync_tables(conn)
        sql = "SELECT * FROM mobile_corrections WHERE status=?"
        params: List[Any] = [status]
        if project_id:
            sql += " AND project_id=?"
            params.append(project_id)
        sql += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def mark_applied(ids: List[int], db_path: Optional[str | Path] = None) -> None:
    if not ids:
        return
    conn = get_connection(db_path)
    try:
        ensure_sync_tables(conn)
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE mobile_corrections SET status='applied', synced_at=datetime('now','localtime') "
            f"WHERE id IN ({placeholders})",
            ids,
        )
        conn.commit()
        bump_revision(db_path)
    finally:
        conn.close()


def export_corrections_json(
    out_path: Optional[str | Path] = None,
    *,
    project_id: Optional[str] = None,
    db_path: Optional[str | Path] = None,
) -> Path:
    rows = list_corrections(project_id=project_id, status="pending", db_path=db_path)
    out = Path(out_path or ROOT / "data" / "sync" / f"mobile_corrections_{datetime.now():%Y%m%d_%H%M%S}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    mark_applied([r["id"] for r in rows], db_path=db_path)
    return out
