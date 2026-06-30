# -*- coding: utf-8 -*-
"""构建手机端同步包：每条清单含名称+特征+单位+AI价+金标准（若有）。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.ingest.parser import parse_workbook
from src.knowledge.calibration import (
    _resolve_path,
    get_pair,
    load_priced_map,
    load_project_pairs,
    run_pair_calibration,
)
from src.link.dedupe import make_dedupe_key
from src.pricing.reconcile import component_total
from src.sync.corrections import bump_revision, ensure_sync_tables
from src.db.database import get_connection

ROOT = Path(__file__).resolve().parents[2]


def _line_dict(line, *, gold: Optional[dict] = None) -> dict:
    nn, un, sig = make_dedupe_key(line.name, line.feature or "", line.unit)
    key = f"{nn}|{sig}|{un}"
    comps = {
        "material_main": line.material_main,
        "material_loss_rate": line.material_loss_rate,
        "material_aux": line.material_aux,
        "labor": line.labor,
        "machinery": line.machinery,
    }
    cost = line.cost_unit_price
    if cost is None:
        cost = component_total(
            {
                "material_main": line.material_main or 0,
                "material_loss_rate": line.material_loss_rate or 0,
                "material_aux": line.material_aux or 0,
                "labor": line.labor or 0,
                "machinery": line.machinery or 0,
            }
        )
    row = {
        "dedupe_key": key,
        "name": line.name,
        "feature": line.feature or "",
        "unit": line.unit,
        "quantity": line.quantity,
        "sheet": line.sheet_name,
        "ai": {
            "cost_unit": cost,
            "material_main": line.material_main,
            "labor": line.labor,
            "material_aux": line.material_aux,
            "machinery": line.machinery,
        },
    }
    if gold:
        row["gold"] = gold
        uc, ac = gold.get("cost_unit"), cost
        if uc and ac and uc > 0:
            row["pct_diff"] = round((ac - uc) / uc * 100, 1)
    return row


def _gold_map_for_pair(pair: dict) -> Dict[str, dict]:
    gold_path = pair.get("gold")
    if not gold_path:
        return {}
    p = ROOT / gold_path if not Path(gold_path).is_absolute() else Path(gold_path)
    if not p.exists():
        return {}
    out: Dict[str, dict] = {}
    for v in load_priced_map(p).values():
        out[v.dedupe_key] = {
            "cost_unit": v.cost_unit,
            "material_main": v.material_main,
            "labor": v.labor,
            "material_aux": v.material_aux,
        }
    return out


def build_project_lines(pair: dict) -> List[dict]:
    export_paths: List[Path] = []
    exports = pair.get("exports") or []
    if exports:
        export_paths = [_resolve_path(p) for p in exports if _resolve_path(p).exists()]
    elif pair.get("export"):
        p = _resolve_path(pair["export"])
        if p.exists():
            export_paths = [p]
    if not export_paths:
        return []
    gold = _gold_map_for_pair(pair)
    lines: List[dict] = []
    seen = set()
    for export_path in export_paths:
        wb = parse_workbook(export_path)
        for line in wb.lines:
            if not line.name or not line.unit:
                continue
            if not line.has_cost_detail and not (line.cost_unit_price and line.cost_unit_price > 0):
                continue
            nn, un, sig = make_dedupe_key(line.name, line.feature or "", line.unit)
            key = f"{nn}|{sig}|{un}"
            if key in seen:
                continue
            seen.add(key)
            g = gold.get(key)
            lines.append(_line_dict(line, gold=g))
    lines.sort(key=lambda x: abs(x.get("pct_diff") or 0), reverse=True)
    return lines


def build_sync_bundle(*, project_id: Optional[str] = None) -> dict:
    pairs = load_project_pairs()
    if project_id:
        pair = get_pair(project_id)
        pairs = [pair] if pair else []

    projects: List[dict] = []
    calibration_summaries: List[dict] = []

    for pair in pairs:
        if not pair:
            continue
        pid = pair.get("id", "")
        lines = build_project_lines(pair)
        cal = None
        try:
            report = run_pair_calibration(pid)
            cal = {
                "compared": report.compared,
                "within_10pct": report.within_10pct,
                "amount_user": report.amount_user,
                "amount_ai": report.amount_ai,
                "amount_diff_pct": round(
                    (report.amount_ai - report.amount_user) / report.amount_user * 100, 1
                )
                if report.amount_user
                else None,
            }
            calibration_summaries.append({"project_id": pid, **cal})
        except Exception:
            cal = None

        projects.append(
            {
                "id": pid,
                "label": pair.get("label", pid),
                "city": pair.get("city", ""),
                "tier": pair.get("tier", "mid"),
                "export": pair.get("export"),
                "line_count": len(lines),
                "calibration": cal,
                "lines": lines,
            }
        )

    conn = get_connection()
    try:
        ensure_sync_tables(conn)
    finally:
        conn.close()
    rev = bump_revision()

    return {
        "revision": rev,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "principle": "每条清单须对照名称+项目特征+单位才能组价",
        "projects": projects,
        "calibration_summaries": calibration_summaries,
    }


def write_sync_bundle(
    out_path: Optional[str | Path] = None,
    *,
    project_id: Optional[str] = None,
) -> Path:
    bundle = build_sync_bundle(project_id=project_id)
    out = Path(out_path or ROOT / "data" / "sync" / "latest_bundle.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    conn = get_connection()
    try:
        ensure_sync_tables(conn)
        conn.execute(
            "UPDATE sync_meta SET bundle_path=?, updated_at=datetime('now','localtime') WHERE id=1",
            (str(out),),
        )
        conn.commit()
    finally:
        conn.close()
    return out
