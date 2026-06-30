"""批量回测人材机判断准确率（与历史成本拆解对比）。"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.db.database import get_connection, resolve_db_path
from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.normalize.craft_classifier import classify_craft
from src.pricing.component_judge import judge_line_components
from src.pricing.cost_basis import get_net_divisor
from src.pricing.engine import PricingEngine
from src.pricing.reconcile import component_total, reconcile_components_with_stored_total

_COMPONENTS = ("material_main", "material_aux", "labor", "machinery")


@dataclass
class AuditSample:
    record_id: int
    standard_item_id: int
    project_id: int
    name: str
    feature: str
    unit: str
    city: str
    price_tier: str
    actual: Dict[str, float]
    actual_total: float
    material_loss_rate: float = 0.0


@dataclass
class AuditRowResult:
    sample: AuditSample
    pred: Dict[str, float]
    pred_total: float
    confidence: float
    auto_fill_ok: bool
    source: str
    craft_label: str
    comp_ok: Dict[str, bool]
    total_ok: bool
    core_ok: bool
    strict_ok: bool


def _rel_err(pred: float, actual: float) -> float:
    if actual <= 0.01:
        return 0.0 if pred <= 0.01 else 1.0
    return abs(pred - actual) / actual


def _component_ok(
    pred: float,
    actual: float,
    *,
    rel_tol: float = 0.20,
    abs_tol: float = 5.0,
) -> bool:
    if actual <= 0.01:
        return pred <= abs_tol
    return _rel_err(pred, actual) <= rel_tol


def load_audit_samples(
    conn,
    *,
    min_total: float = 1.0,
    limit: Optional[int] = None,
    project_id: Optional[int] = None,
) -> List[AuditSample]:
    where = " AND cr.cost_unit_price >= ? "
    params: list = [min_total]
    if project_id is not None:
        where += " AND cr.source_project_id=? "
        params.append(project_id)

    sql = f"""
        SELECT cr.id AS record_id, cr.standard_item_id, cr.source_project_id AS project_id,
               COALESCE(bl.name, si.name_norm) AS name,
               COALESCE(bl.feature, '') AS feature,
               COALESCE(bl.unit, si.unit_norm) AS unit,
               COALESCE(p.city, '') AS city,
               COALESCE(p.price_tier, 'mid') AS price_tier,
               cr.material_main, cr.material_aux, cr.labor, cr.machinery,
               cr.material_loss_rate, cr.cost_unit_price
        FROM cost_records cr
        JOIN standard_items si ON si.id = cr.standard_item_id
        LEFT JOIN boq_lines bl ON bl.id = cr.source_line_id
        JOIN projects p ON p.id = cr.source_project_id
        WHERE 1=1 {where}
        ORDER BY cr.id
    """
    rows = conn.execute(sql, params).fetchall()
    samples: List[AuditSample] = []
    for r in rows:
        actual = {
            "material_main": float(r["material_main"] or 0),
            "material_aux": float(r["material_aux"] or 0),
            "labor": float(r["labor"] or 0),
            "machinery": float(r["machinery"] or 0),
        }
        total = float(r["cost_unit_price"] or 0)
        if total < min_total:
            continue
        if sum(actual.values()) <= 0:
            continue
        samples.append(
            AuditSample(
                record_id=int(r["record_id"]),
                standard_item_id=int(r["standard_item_id"]),
                project_id=int(r["project_id"]),
                name=r["name"] or "",
                feature=r["feature"] or "",
                unit=r["unit"] or "",
                city=r["city"] or "",
                price_tier=r["price_tier"] or "mid",
                actual=actual,
                actual_total=total,
                material_loss_rate=float(r["material_loss_rate"] or 0),
            )
        )
    if limit and len(samples) > limit:
        step = max(1, len(samples) // limit)
        samples = samples[::step][:limit]
    return samples


def _expected_display_total(
    sample: AuditSample,
    *,
    net_divisor: float,
) -> float:
    """与用户成本区一致的目标合价（含净价/毛价口径）。"""
    comps = {
        **sample.actual,
        "material_loss_rate": sample.material_loss_rate,
    }
    out = reconcile_components_with_stored_total(
        comps,
        sample.actual_total,
        net_divisor=net_divisor,
        unit=sample.unit,
        name=sample.name,
        feature=sample.feature,
    )
    return component_total(out)


def _evaluate_row(
    sample: AuditSample,
    judgment,
    *,
    rel_tol: float,
    abs_tol: float,
    total_rel_tol: float,
    net_divisor: float,
) -> AuditRowResult:
    pred = judgment.as_components()
    pred_total = component_total(
        {**pred, "material_loss_rate": judgment.material_loss_rate}
    )
    expected_total = _expected_display_total(sample, net_divisor=net_divisor)
    comp_ok = {
        k: _component_ok(pred.get(k) or 0, sample.actual.get(k) or 0, rel_tol=rel_tol, abs_tol=abs_tol)
        for k in _COMPONENTS
    }
    total_ok = _rel_err(pred_total, expected_total) <= total_rel_tol
    core_ok = comp_ok["material_main"] and comp_ok["labor"]
    strict_ok = all(comp_ok.values()) and total_ok
    return AuditRowResult(
        sample=sample,
        pred=pred,
        pred_total=pred_total,
        confidence=judgment.confidence,
        auto_fill_ok=judgment.auto_fill_ok,
        source=judgment.source,
        craft_label=judgment.craft_label,
        comp_ok=comp_ok,
        total_ok=total_ok,
        core_ok=core_ok,
        strict_ok=strict_ok,
    )


def run_judge_audit(
    db_path: Optional[str] = None,
    *,
    exclude_self: bool = True,
    rel_tol: float = 0.20,
    abs_tol: float = 5.0,
    total_rel_tol: float = 0.15,
    limit: Optional[int] = None,
    project_id: Optional[int] = None,
    export_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    对历史 cost_records 回测 judge_line_components。
    exclude_self=True 时排除同 standard_item，避免整项匹配「套自己」。
    """
    conn = get_connection(db_path)
    repo = KnowledgeRepository(db_path)
    engine = PricingEngine(db_path)
    net_divisor = get_net_divisor(repo.settings.get("pricing", {}))
    try:
        samples = load_audit_samples(conn, limit=limit, project_id=project_id)
    finally:
        conn.close()

    results: List[AuditRowResult] = []
    total_s = len(samples)
    for i, s in enumerate(samples, 1):
        if total_s >= 500 and i % 500 == 0:
            print(f"  回测进度 {i}/{total_s}...", flush=True)
        ctx = PricingContext(city=s.city, price_tier=s.price_tier)
        ex = s.standard_item_id if exclude_self else None
        j = judge_line_components(
            s.name,
            s.feature,
            s.unit,
            engine,
            repo,
            ctx=ctx,
            exclude_standard_item_id=ex,
        )
        results.append(
            _evaluate_row(
                s, j, rel_tol=rel_tol, abs_tol=abs_tol, total_rel_tol=total_rel_tol,
                net_divisor=net_divisor,
            )
        )

    n = len(results)
    if n == 0:
        return {"samples": 0, "message": "无可用成本样本"}

    def pct(count: int) -> float:
        return round(count / n, 4)

    auto_rows = [r for r in results if r.auto_fill_ok]
    auto_n = len(auto_rows)

    summary = {
        "samples": n,
        "exclude_self": exclude_self,
        "tolerance": {
            "component_rel": rel_tol,
            "component_abs_yuan": abs_tol,
            "total_rel": total_rel_tol,
        },
        "auto_fill_count": auto_n,
        "auto_fill_rate": pct(auto_n),
        "accuracy_all": {
            "strict_component_and_total": pct(sum(1 for r in results if r.strict_ok)),
            "core_main_and_labor": pct(sum(1 for r in results if r.core_ok)),
            "total_cost": pct(sum(1 for r in results if r.total_ok)),
            "material_main": pct(sum(1 for r in results if r.comp_ok["material_main"])),
            "labor": pct(sum(1 for r in results if r.comp_ok["labor"])),
            "material_aux": pct(sum(1 for r in results if r.comp_ok["material_aux"])),
            "machinery": pct(sum(1 for r in results if r.comp_ok["machinery"])),
        },
        "accuracy_auto_fill_only": {},
        "by_source": {},
        "by_craft": {},
        "confidence_median": round(
            statistics.median([r.confidence for r in results]), 4
        ),
        "target_80_met": False,
    }

    if auto_n > 0:
        summary["accuracy_auto_fill_only"] = {
            "strict": round(sum(1 for r in auto_rows if r.strict_ok) / auto_n, 4),
            "core_main_labor": round(sum(1 for r in auto_rows if r.core_ok) / auto_n, 4),
            "total_cost": round(sum(1 for r in auto_rows if r.total_ok) / auto_n, 4),
        }
        summary["target_80_met"] = summary["accuracy_auto_fill_only"]["core_main_labor"] >= 0.80

    summary["target_80_total_all"] = summary["accuracy_all"]["total_cost"] >= 0.80

    by_src: Dict[str, List[AuditRowResult]] = {}
    by_craft: Dict[str, List[AuditRowResult]] = {}
    for r in results:
        by_src.setdefault(r.source, []).append(r)
        craft = classify_craft(r.sample.name, r.sample.feature, r.sample.unit).label
        by_craft.setdefault(craft, []).append(r)

    for src, rows in sorted(by_src.items(), key=lambda x: -len(x[1])):
        summary["by_source"][src] = {
            "count": len(rows),
            "core_ok_rate": round(sum(1 for x in rows if x.core_ok) / len(rows), 4),
            "strict_ok_rate": round(sum(1 for x in rows if x.strict_ok) / len(rows), 4),
            "auto_fill_rate": round(sum(1 for x in rows if x.auto_fill_ok) / len(rows), 4),
        }

    for craft, rows in sorted(by_craft.items(), key=lambda x: -len(x[1]))[:15]:
        summary["by_craft"][craft] = {
            "count": len(rows),
            "core_ok_rate": round(sum(1 for x in rows if x.core_ok) / len(rows), 4),
            "auto_fill_rate": round(sum(1 for x in rows if x.auto_fill_ok) / len(rows), 4),
        }

    if export_path:
        _export_audit_excel(results, Path(export_path), summary, net_divisor=net_divisor)

    return summary


def _export_audit_excel(
    results: List[AuditRowResult],
    path: Path,
    summary: dict,
    *,
    net_divisor: float = 1.1,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for r in results:
        s = r.sample
        rows.append(
            {
                "record_id": s.record_id,
                "项目名称": s.name[:80],
                "单位": s.unit,
                "城市": s.city,
                "档位": s.price_tier,
                "工艺": r.craft_label,
                "判断来源": r.source,
                "置信度": round(r.confidence, 3),
                "可自动填": r.auto_fill_ok,
                "实_主材": s.actual["material_main"],
                "判_主材": r.pred.get("material_main"),
                "主材OK": r.comp_ok["material_main"],
                "实_人工": s.actual["labor"],
                "判_人工": r.pred.get("labor"),
                "人工OK": r.comp_ok["labor"],
                "实_辅材": s.actual["material_aux"],
                "判_辅材": r.pred.get("material_aux"),
                "实_机械": s.actual["machinery"],
                "判_机械": r.pred.get("machinery"),
                "实_合计": s.actual_total,
                "期望_合计": round(
                    _expected_display_total(s, net_divisor=net_divisor), 2
                ),
                "判_合计": round(r.pred_total, 2),
                "合计OK": r.total_ok,
                "核心OK": r.core_ok,
                "严格OK": r.strict_ok,
            }
        )
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="明细", index=False)
        sum_rows = []
        for k, v in summary.get("accuracy_all", {}).items():
            sum_rows.append({"指标": k, "全样本": v})
        if summary.get("accuracy_auto_fill_only"):
            for k, v in summary["accuracy_auto_fill_only"].items():
                sum_rows.append({"指标": f"auto_fill_{k}", "全样本": v})
        sum_rows.append({"指标": "auto_fill_rate", "全样本": summary.get("auto_fill_rate")})
        sum_rows.append({"指标": "samples", "全样本": summary.get("samples")})
        sum_rows.append({"指标": "target_80_core_met", "全样本": summary.get("target_80_met")})
        pd.DataFrame(sum_rows).to_excel(w, sheet_name="汇总", index=False)
        src_rows = [
            {"来源": k, **v} for k, v in summary.get("by_source", {}).items()
        ]
        if src_rows:
            pd.DataFrame(src_rows).to_excel(w, sheet_name="按来源", index=False)
        craft_rows = [
            {"工艺": k, **v} for k, v in summary.get("by_craft", {}).items()
        ]
        if craft_rows:
            pd.DataFrame(craft_rows).to_excel(w, sheet_name="按工艺", index=False)
