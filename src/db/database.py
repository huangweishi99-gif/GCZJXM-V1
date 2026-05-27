"""SQLite 数据库：历史造价知识库 + 组价任务。"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB = _ROOT / "data" / "cost_pricing.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    project_type    TEXT NOT NULL DEFAULT 'historical',
    source_file     TEXT,
    region          TEXT,
    remark          TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS boq_lines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    sheet_name      TEXT,
    section_path    TEXT,
    seq             TEXT,
    list_code       TEXT,
    name            TEXT NOT NULL,
    feature         TEXT,
    unit            TEXT,
    quantity        REAL,
    unit_price      REAL,
    amount          REAL,
    remark          TEXT,
    name_norm       TEXT,
    feature_norm    TEXT,
    unit_norm       TEXT,
    method_signature TEXT,
    method_summary  TEXT,
    row_index       INTEGER
);

CREATE TABLE IF NOT EXISTS standard_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    list_code           TEXT,
    name_norm           TEXT NOT NULL,
    feature_norm        TEXT NOT NULL DEFAULT '',
    unit_norm           TEXT NOT NULL,
    feature_fingerprint TEXT,
    method_signature    TEXT NOT NULL DEFAULT '_generic',
    feature_tags_json   TEXT,
    method_summary      TEXT,
    sample_count        INTEGER NOT NULL DEFAULT 0,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(name_norm, unit_norm, method_signature)
);

CREATE TABLE IF NOT EXISTS cost_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_item_id    INTEGER NOT NULL REFERENCES standard_items(id) ON DELETE CASCADE,
    source_project_id   INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    source_line_id      INTEGER REFERENCES boq_lines(id) ON DELETE SET NULL,
    material_main       REAL NOT NULL DEFAULT 0,
    material_loss_rate  REAL NOT NULL DEFAULT 0,
    material_aux        REAL NOT NULL DEFAULT 0,
    labor               REAL NOT NULL DEFAULT 0,
    machinery           REAL NOT NULL DEFAULT 0,
    management          REAL NOT NULL DEFAULT 0,
    profit              REAL NOT NULL DEFAULT 0,
    tax                 REAL NOT NULL DEFAULT 0,
    cost_unit_price     REAL NOT NULL,
    unit_price          REAL,
    recorded_at         TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    is_verified         INTEGER NOT NULL DEFAULT 0,
    note                TEXT
);

CREATE TABLE IF NOT EXISTS pricing_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'draft',
    output_file     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS pricing_lines (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              INTEGER NOT NULL REFERENCES pricing_jobs(id) ON DELETE CASCADE,
    boq_line_id         INTEGER NOT NULL REFERENCES boq_lines(id) ON DELETE CASCADE,
    match_level         TEXT NOT NULL DEFAULT 'D',
    confidence          REAL NOT NULL DEFAULT 0,
    standard_item_id    INTEGER REFERENCES standard_items(id),
    source_record_count INTEGER NOT NULL DEFAULT 0,
    material_main       REAL,
    material_loss_rate  REAL,
    material_aux        REAL,
    labor               REAL,
    machinery           REAL,
    management          REAL,
    profit              REAL,
    tax                 REAL,
    cost_unit_price     REAL,
    cost_amount         REAL,
    unit_price          REAL,
    amount              REAL,
    match_note          TEXT
);

CREATE INDEX IF NOT EXISTS idx_boq_project ON boq_lines(project_id);
CREATE INDEX IF NOT EXISTS idx_std_method ON standard_items(name_norm, unit_norm, method_signature);
CREATE INDEX IF NOT EXISTS idx_cost_std ON cost_records(standard_item_id);
CREATE INDEX IF NOT EXISTS idx_pricing_job ON pricing_lines(job_id);
"""

_MIGRATIONS = [
    "ALTER TABLE cost_records ADD COLUMN material_loss_rate REAL NOT NULL DEFAULT 0",
    "ALTER TABLE cost_records ADD COLUMN tax REAL NOT NULL DEFAULT 0",
    "ALTER TABLE pricing_lines ADD COLUMN material_loss_rate REAL",
    "ALTER TABLE pricing_lines ADD COLUMN tax REAL",
    "ALTER TABLE pricing_lines ADD COLUMN cost_amount REAL",
    "ALTER TABLE standard_items ADD COLUMN method_signature TEXT NOT NULL DEFAULT '_generic'",
    "ALTER TABLE standard_items ADD COLUMN feature_tags_json TEXT",
    "ALTER TABLE standard_items ADD COLUMN method_summary TEXT",
    "ALTER TABLE boq_lines ADD COLUMN method_signature TEXT",
    "ALTER TABLE boq_lines ADD COLUMN method_summary TEXT",
]


def resolve_db_path(path: Optional[str | Path] = None) -> Path:
    if path is None:
        return _DEFAULT_DB
    p = Path(path)
    if not p.is_absolute():
        p = _ROOT / p
    return p


def get_connection(db_path: Optional[str | Path] = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    for sql in _MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass


def _has_legacy_unique_on_feature(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='standard_items'"
    ).fetchone()
    if not row or not row[0]:
        return False
    sql = row[0].upper()
    return "FEATURE_NORM" in sql and "UNIQUE" in sql and "METHOD_SIGNATURE" not in sql


def rebuild_standard_items_table(conn: sqlite3.Connection) -> None:
    """移除旧版 (name, feature全文, unit) 唯一约束，改为做法签名唯一。"""
    if not _has_legacy_unique_on_feature(conn):
        return
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        CREATE TABLE standard_items_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_code TEXT,
            name_norm TEXT NOT NULL,
            feature_norm TEXT NOT NULL DEFAULT '',
            unit_norm TEXT NOT NULL,
            feature_fingerprint TEXT,
            method_signature TEXT NOT NULL DEFAULT '_generic',
            feature_tags_json TEXT,
            method_summary TEXT,
            sample_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(name_norm, unit_norm, method_signature)
        );
        INSERT INTO standard_items_new
            (id, list_code, name_norm, feature_norm, unit_norm, feature_fingerprint,
             method_signature, feature_tags_json, method_summary, sample_count, updated_at)
        SELECT id, list_code, name_norm, feature_norm, unit_norm, feature_fingerprint,
               COALESCE(method_signature, '_generic'), feature_tags_json, method_summary,
               sample_count, updated_at
        FROM standard_items;
        DROP TABLE standard_items;
        ALTER TABLE standard_items_new RENAME TO standard_items;
        CREATE INDEX IF NOT EXISTS idx_std_method
            ON standard_items(name_norm, unit_norm, method_signature);
        PRAGMA foreign_keys = ON;
        """
    )


def init_database(db_path: Optional[str | Path] = None) -> Path:
    path = resolve_db_path(db_path)
    conn = get_connection(path)
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        rebuild_standard_items_table(conn)
        conn.commit()
    finally:
        conn.close()
    return path


def reset_database(db_path: Optional[str | Path] = None) -> Path:
    """清空并重建数据库（全量 re-learn 前使用）。"""
    path = resolve_db_path(db_path)
    if path.exists():
        path.unlink()
    return init_database(path)
