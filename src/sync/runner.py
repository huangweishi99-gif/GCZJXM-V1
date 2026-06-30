# -*- coding: utf-8 -*-
"""远程调用 deliver / calibrate（与 app.py 同逻辑）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.export.inplace_bidder import fill_tender_inplace
from src.knowledge.calibration import (
    export_calibration_report,
    get_pair,
    learn_from_gold,
    run_pair_calibration,
)
from src.knowledge.repository import KnowledgeRepository
from src.pricing.engine import PricingEngine
from src.sync.bundle import write_sync_bundle
from src.sync.corrections import export_corrections_json, list_corrections

ROOT = Path(__file__).resolve().parents[2]


def _resolve_file(path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    for d in (
        ROOT / "清单数据资料",
        ROOT / "清单数据资料" / "AI学习清单",
        ROOT / "清单数据资料" / "甲方招标清单",
        ROOT / "data" / "exports",
    ):
        alt = d / Path(path).name
        if not p.exists() and alt.exists():
            p = alt
            break
    if not p.exists():
        raise FileNotFoundError(f"找不到文件: {path}")
    return str(p)


def _run_deliver_one(
    tender: str,
    *,
    city: Optional[str],
    tier: str,
    output: Optional[str],
    match_mode: Optional[str] = None,
) -> dict:
    tender_path = _resolve_file(tender)
    out_path = str(ROOT / output) if output and not Path(output).is_absolute() else output

    repo = KnowledgeRepository()
    result = repo.import_tender(tender_path, city=city, price_tier=tier)
    engine = PricingEngine(match_mode=match_mode)
    pr = engine.run_for_project(result["project_id"])
    written = fill_tender_inplace(
        tender_path,
        pr["job_id"],
        output_path=out_path,
        reference_fill=True,
    )
    return {
        "tender": tender_path,
        "export": written,
        "import": result,
        "pricing": pr,
    }


def run_deliver_project(
    project_id: str,
    *,
    match_mode: Optional[str] = None,
) -> dict:
    pair = get_pair(project_id)
    if not pair:
        raise ValueError(f"未知项目: {project_id}")

    city = pair.get("city")
    tier = pair.get("tier", "mid")
    tender_list = pair.get("tenders") or []
    if not tender_list:
        t = pair.get("tender") or pair.get("tender_fallback")
        tender_list = [t] if t else []
    export_list = pair.get("exports") or []
    if not export_list and pair.get("export"):
        export_list = [pair["export"]]
    if not tender_list:
        raise ValueError(f"项目 {project_id} 未配置 tender")

    outputs: List[dict] = []
    for i, tender in enumerate(tender_list):
        out = export_list[i] if i < len(export_list) else None
        try:
            outputs.append(
                _run_deliver_one(tender, city=city, tier=tier, output=out, match_mode=match_mode)
            )
        except Exception as exc:
            fb = pair.get("tender_fallback")
            if fb and _resolve_file(tender) != _resolve_file(fb):
                outputs.append(
                    _run_deliver_one(fb, city=city, tier=tier, output=out, match_mode=match_mode)
                )
            else:
                raise exc

    bundle_path = write_sync_bundle(project_id=project_id)
    return {
        "project_id": project_id,
        "label": pair.get("label", project_id),
        "outputs": outputs,
        "bundle": str(bundle_path),
    }


def run_calibrate_project(
    project_id: str,
    *,
    rel_tol: float = 0.10,
    learn: bool = False,
) -> dict:
    pair = get_pair(project_id)
    if not pair:
        raise ValueError(f"未知项目: {project_id}")

    report = run_pair_calibration(project_id, rel_tol=rel_tol)
    report_path = export_calibration_report(report)
    payload = {
        "project_id": project_id,
        "label": report.label,
        "compared": report.compared,
        "within_10pct": report.within_10pct,
        "amount_diff_pct": round(
            (report.amount_ai - report.amount_user) / report.amount_user * 100, 1
        )
        if report.amount_user
        else None,
        "report": report_path,
    }
    if learn and pair.get("gold"):
        r = learn_from_gold(
            _resolve_file(pair["gold"]),
            city=pair.get("city", ""),
            tier=pair.get("tier", "mid"),
        )
        payload["learn"] = r
    write_sync_bundle(project_id=project_id)
    return payload


def run_sync_pull(project_id: Optional[str] = None) -> dict:
    pending = list_corrections(project_id=project_id, status="pending")
    if not pending:
        return {"count": 0, "path": None}
    path = export_corrections_json(project_id=project_id)
    return {"count": len(pending), "path": str(path)}
