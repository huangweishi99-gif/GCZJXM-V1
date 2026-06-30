# -*- coding: utf-8 -*-
"""
用户校正闭环：对比「系统导出 vs AI学习清单金标准」，生成升级建议并驱动 learn。
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.ingest.parser import parse_workbook
from src.link.dedupe import make_dedupe_key
from src.pricing.reconcile import component_total

ROOT = Path(__file__).resolve().parents[2]
PAIRS_PATH = ROOT / "config" / "project_pairs.json"


@dataclass
class PricedRow:
    dedupe_key: str
    name: str
    feature: str
    unit: str
    quantity: float
    cost_unit: float
    material_main: Optional[float] = None
    labor: Optional[float] = None
    material_aux: Optional[float] = None
    sheet: str = ""


@dataclass
class LineDiff:
    dedupe_key: str
    name: str
    unit: str
    feature: str
    qty: float
    user_cost: float
    ai_cost: float
    pct_diff: Optional[float]
    user_main: Optional[float] = None
    ai_main: Optional[float] = None
    user_labor: Optional[float] = None
    ai_labor: Optional[float] = None


@dataclass
class CalibrationReport:
    project_id: str
    label: str
    gold_file: str
    ai_file: str
    compared: int = 0
    within_5pct: int = 0
    within_10pct: int = 0
    within_20pct: int = 0
    user_only: int = 0
    ai_only: int = 0
    amount_user: float = 0.0
    amount_ai: float = 0.0
    worst: List[LineDiff] = field(default_factory=list)
    clusters: Dict[str, int] = field(default_factory=dict)
    upgrade_actions: List[str] = field(default_factory=list)


def _resolve_path(rel: str) -> Path:
    p = Path(rel)
    if not p.is_absolute():
        p = ROOT / rel
    return p


def load_project_pairs() -> List[dict]:
    if not PAIRS_PATH.exists():
        return []
    return json.loads(PAIRS_PATH.read_text(encoding="utf-8")).get("pairs", [])


def get_pair(pair_id: str) -> Optional[dict]:
    for p in load_project_pairs():
        if p.get("id") == pair_id:
            return p
    return None


def _line_cost_unit(line) -> Optional[float]:
    if line.cost_unit_price and line.cost_unit_price > 0:
        return float(line.cost_unit_price)
    comps = {
        "material_main": line.material_main or 0,
        "material_loss_rate": line.material_loss_rate or 0,
        "material_aux": line.material_aux or 0,
        "labor": line.labor or 0,
        "machinery": line.machinery or 0,
    }
    if any(comps[k] for k in ("material_main", "labor", "material_aux", "machinery")):
        return component_total(comps)
    return None


def load_priced_map(path: str | Path) -> Dict[str, PricedRow]:
    """按 dedupe_key 加载有成本单价的清单行（同键取首条有价行）。"""
    wb = parse_workbook(path)
    out: Dict[str, PricedRow] = {}
    for line in wb.lines:
        if not line.name or not line.unit:
            continue
        cu = _line_cost_unit(line)
        if cu is None or cu <= 0:
            continue
        nn, un, sig = make_dedupe_key(line.name, line.feature or "", line.unit)
        key = f"{nn}|{sig}|{un}"
        if key in out:
            continue
        out[key] = PricedRow(
            dedupe_key=key,
            name=line.name.split("\n")[0][:80],
            feature=(line.feature or "")[:200],
            unit=line.unit,
            quantity=float(line.quantity or 0),
            cost_unit=round(cu, 4),
            material_main=line.material_main,
            labor=line.labor,
            material_aux=line.material_aux,
            sheet=line.sheet_name,
        )
    return out


def load_priced_map_merged(paths: List[str | Path]) -> Dict[str, PricedRow]:
    """合并多份导出/招标的成本 map（同键后者覆盖并记录来源）。"""
    merged: Dict[str, PricedRow] = {}
    for p in paths:
        for k, row in load_priced_map(p).items():
            merged[k] = row
    return merged


def _compare_maps(
    gold_map: Dict[str, PricedRow],
    ai_map: Dict[str, PricedRow],
    *,
    project_id: str = "",
    label: str = "",
    gold_file: str = "",
    ai_file: str = "",
) -> CalibrationReport:
    report = CalibrationReport(
        project_id=project_id,
        label=label,
        gold_file=gold_file,
        ai_file=ai_file,
    )
    report.user_only = len(set(gold_map) - set(ai_map))
    report.ai_only = len(set(ai_map) - set(gold_map))

    diffs: List[LineDiff] = []
    for key, u in gold_map.items():
        a = ai_map.get(key)
        if not a:
            continue
        pct = round((a.cost_unit - u.cost_unit) / u.cost_unit * 100, 1) if u.cost_unit else None
        diffs.append(
            LineDiff(
                dedupe_key=key,
                name=u.name,
                unit=u.unit,
                feature=u.feature[:120],
                qty=u.quantity,
                user_cost=u.cost_unit,
                ai_cost=a.cost_unit,
                pct_diff=pct,
                user_main=u.material_main,
                ai_main=a.material_main,
                user_labor=u.labor,
                ai_labor=a.labor,
            )
        )

    uniq: Dict[str, LineDiff] = {}
    for d in diffs:
        if d.dedupe_key not in uniq:
            uniq[d.dedupe_key] = d

    report.compared = len(uniq)
    for d in uniq.values():
        if d.pct_diff is None:
            continue
        if abs(d.pct_diff) <= 5:
            report.within_5pct += 1
        if abs(d.pct_diff) <= 10:
            report.within_10pct += 1
        if abs(d.pct_diff) <= 20:
            report.within_20pct += 1

    report.amount_user = round(
        sum(d.user_cost * d.qty for d in uniq.values() if d.qty), 2
    )
    report.amount_ai = round(
        sum(d.ai_cost * d.qty for d in uniq.values() if d.qty), 2
    )
    report.worst = sorted(
        uniq.values(),
        key=lambda x: abs(x.pct_diff or 0),
        reverse=True,
    )[:20]

    # 按名称关键词聚类大偏差（≥20%）
    cluster: Counter = Counter()
    for d in uniq.values():
        if d.pct_diff is not None and abs(d.pct_diff) >= 20:
            tag = _cluster_tag(d.name)
            cluster[tag] += 1
    report.clusters = dict(cluster.most_common(15))
    report.upgrade_actions = _suggest_upgrades(report, uniq)
    return report


def compare_calibration(
    gold_path: str | Path,
    ai_path: str | Path,
    *,
    project_id: str = "",
    label: str = "",
    rel_tol: float = 0.10,
) -> CalibrationReport:
    return _compare_maps(
        load_priced_map(gold_path),
        load_priced_map(ai_path),
        project_id=project_id,
        label=label,
        gold_file=str(gold_path),
        ai_file=str(ai_path),
    )


def compare_calibration_merged(
    gold_path: str | Path,
    ai_paths: List[str | Path],
    *,
    project_id: str = "",
    label: str = "",
) -> CalibrationReport:
    return _compare_maps(
        load_priced_map(gold_path),
        load_priced_map_merged(ai_paths),
        project_id=project_id,
        label=label,
        gold_file=str(gold_path),
        ai_file=";".join(str(p) for p in ai_paths),
    )


def _cluster_tag(name: str) -> str:
    keys = (
        ("PT-", "涂料PT编号"),
        ("MT-", "金属线条MT"),
        ("ST-", "石材ST"),
        ("吊顶", "吊顶"),
        ("门", "定制门"),
        ("地砖", "地砖"),
        ("防水", "防水"),
        ("乳胶漆", "乳胶漆"),
        ("无机涂料", "涂料"),
    )
    for kw, tag in keys:
        if kw in name:
            return tag
    return "其他"


def _suggest_upgrades(report: CalibrationReport, uniq: Dict[str, LineDiff]) -> List[str]:
    actions: List[str] = []
    if report.compared and report.within_10pct / report.compared >= 0.8:
        actions.append(
            f"招标范围准确率 {report.within_10pct}/{report.compared} 已达80%目标，可 learn 固化"
        )
    elif report.compared:
        actions.append(
            f"准确率 {report.within_10pct}/{report.compared} 未达80%："
            "优先 learn 金标准 → backfill-kb → 补 market_reference / 工序规则"
        )
    for tag, cnt in report.clusters.items():
        if cnt >= 2:
            if tag == "涂料PT编号":
                actions.append(f"[{tag}] {cnt}项：检查 material_process_price 工序分解与 PT 表价口径")
            elif tag == "金属线条MT":
                actions.append(f"[{tag}] {cnt}项：检查 MT 层0跳过 + metal_trim 展开面插值")
            elif tag == "吊顶":
                actions.append(f"[{tag}] {cnt}项：补不锈钢/古铜吊顶 market 或历史样本")
            elif tag == "定制门":
                actions.append(f"[{tag}] {cnt}项：扩充 custom_door 价库或 learn 门套样本")
            else:
                actions.append(f"[{tag}] {cnt}项大偏差：python app.py external-price --from-calibration")
    if report.user_only:
        actions.append(f"金标准有 {report.user_only} 项系统未填价：检查 tender 导出是否漏行/漏 sheet")
    if report.ai_only:
        actions.append(f"系统多填 {report.ai_only} 项金标准无价：可能是 AI 误填或金标准未覆盖")
    amt_pct = (
        round((report.amount_ai - report.amount_user) / report.amount_user * 100, 1)
        if report.amount_user
        else None
    )
    if amt_pct is not None and abs(amt_pct) > 10:
        actions.append(f"合价总量偏差 {amt_pct}%：检查管理费/净价折算 reconcile 逻辑")
    return actions


def run_pair_calibration(pair_id: str, *, rel_tol: float = 0.10) -> CalibrationReport:
    pair = get_pair(pair_id)
    if not pair:
        raise ValueError(f"未知项目 id: {pair_id}（见 config/project_pairs.json）")
    gold = _resolve_path(pair["gold"])
    if not gold.exists():
        raise FileNotFoundError(f"金标准不存在: {gold}")

    exports = pair.get("exports") or []
    if exports:
        ai_paths = [_resolve_path(p) for p in exports]
        missing = [p for p in ai_paths if not p.exists()]
        if missing:
            raise FileNotFoundError(
                f"系统导出缺失 {len(missing)} 个文件，请先: python app.py deliver --project {pair_id}\n"
                + "\n".join(str(p) for p in missing)
            )
        return compare_calibration_merged(
            gold,
            ai_paths,
            project_id=pair_id,
            label=pair.get("label", pair_id),
        )

    ai = _resolve_path(pair["export"])
    if not ai.exists():
        raise FileNotFoundError(
            f"系统导出不存在: {ai}，请先运行: python app.py deliver --project {pair_id}"
        )
    return compare_calibration(
        gold,
        ai,
        project_id=pair_id,
        label=pair.get("label", pair_id),
        rel_tol=rel_tol,
    )


def export_calibration_report(report: CalibrationReport, output: Optional[str] = None) -> str:
    out_dir = ROOT / "data" / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    if output:
        path = Path(output)
        if not path.is_absolute():
            path = ROOT / path
    else:
        path = out_dir / f"校准报告_{report.project_id}_{date.today():%Y%m%d}.json"

    payload = asdict(report)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def learn_from_gold(gold_path: str | Path, *, city: str = "", tier: str = "mid") -> dict:
    from src.knowledge.repository import KnowledgeRepository

    repo = KnowledgeRepository()
    return repo.learn_from_file(
        str(_resolve_path(str(gold_path)) if not Path(gold_path).is_absolute() else gold_path),
        city=city or None,
        price_tier=tier or None,
        export_anatomy=True,
    )
