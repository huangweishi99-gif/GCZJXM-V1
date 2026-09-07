# -*- coding: utf-8 -*-
"""从 audit-judge 明细生成待确认清单。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


DEFAULT_AUDIT_PATH = Path("data/exports/抽检报告_人材机判断.xlsx")
DEFAULT_REVIEW_PATH = Path("data/exports/待确认清单_人材机判断.xlsx")
PROJECT_CODE_RE = re.compile(
    r"(?<![A-Za-z])(?:ST|CT|WD|PT|MT|GL|AL|CL|SF|FA)\s*-?\s*\d+(?:\.\d+)?",
    re.I,
)


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def _num(v: Any) -> float:
    try:
        if pd.isna(v):
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def _rel_err(pred: float, actual: float) -> float:
    if abs(actual) <= 0.01:
        return 0.0 if abs(pred) <= 0.01 else 1.0
    return abs(pred - actual) / abs(actual)


def _project_code_sensitive(name: str) -> bool:
    return bool(PROJECT_CODE_RE.search(name or ""))


def _package_like(name: str) -> bool:
    return bool(re.search(r"脚手架|措施费|验收|系统接入|设计费|调试|包干", name or ""))


def _risk_for_row(row: pd.Series) -> Dict[str, Any]:
    name = str(row.get("项目名称", "") or "")
    source = str(row.get("判断来源", "") or "")
    auto_fill = _as_bool(row.get("可自动填"))
    core_ok = _as_bool(row.get("核心OK"))
    strict_ok = _as_bool(row.get("严格OK"))
    total_ok = _as_bool(row.get("合计OK"))
    main_ok = _as_bool(row.get("主材OK"))
    labor_ok = _as_bool(row.get("人工OK"))
    confidence = _num(row.get("置信度"))

    tags: List[str] = []
    score = 0
    if auto_fill and not core_ok:
        tags.append("自动填但核心不准")
        score += 100
    if source == "unresolved":
        tags.append("缺历史样本")
        score += 80
    if not core_ok:
        tags.append("主材/人工核心偏差")
        score += 60
    if source == "line_match_weak":
        tags.append("弱历史匹配")
        score += 38
    if source == "market_reference":
        tags.append("仅市场参考")
        score += 30
    if source in ("material_plus_template", "craft_profile"):
        tags.append("模板拆分需复核")
        score += 35
    if not strict_ok:
        tags.append("分项或合计未全准")
        score += 18
    if not total_ok:
        tags.append("合计偏差")
        score += 15
    if confidence < 0.75:
        tags.append("低置信")
        score += 10
    if _project_code_sensitive(name):
        tags.append("项目编号敏感")
        score += 20
    if _package_like(name):
        tags.append("包干/措施项")
        score += 25

    main_err = _rel_err(_num(row.get("判_主材")), _num(row.get("实_主材")))
    labor_err = _rel_err(_num(row.get("判_人工")), _num(row.get("实_人工")))
    total_err = _rel_err(_num(row.get("判_合计")), _num(row.get("期望_合计") or row.get("实_合计")))
    max_err = max(main_err, labor_err, total_err)
    if max_err > 1.0:
        score += 15
    elif max_err > 0.5:
        score += 8

    if not tags:
        tags.append("抽样复核")

    if auto_fill and not core_ok:
        action = "优先修规则或降低自动填置信；交付前必须人工确认"
    elif source == "unresolved":
        action = "补历史样本或新增专项规则；暂不自动填"
    elif source == "market_reference":
        action = "确认是否应沉淀为城市/项目定稿价"
    elif source == "line_match_weak":
        action = "核对相似历史项名称、特征、单位是否真一致"
    elif source in ("material_plus_template", "craft_profile"):
        action = "检查主材价库和工艺份额模板是否适用"
    else:
        action = "人工复核分项拆分，必要时补专项规则"

    return {
        "风险分": score,
        "风险标签": "、".join(dict.fromkeys(tags)),
        "建议动作": action,
        "主材误差": round(main_err, 4),
        "人工误差": round(labor_err, 4),
        "合计误差": round(total_err, 4),
    }


def build_audit_review(
    audit_path: str | Path = DEFAULT_AUDIT_PATH,
    *,
    output_path: str | Path = DEFAULT_REVIEW_PATH,
    json_path: Optional[str | Path] = None,
    top: int = 80,
) -> Dict[str, Any]:
    """读取 audit-judge 明细，生成待确认 Excel 和可选 JSON 摘要。"""
    audit_path = Path(audit_path)
    output_path = Path(output_path)
    if not audit_path.exists():
        raise FileNotFoundError(f"找不到抽检报告: {audit_path}")

    df = pd.read_excel(audit_path, sheet_name="明细")
    risk_rows = [_risk_for_row(row) for _, row in df.iterrows()]
    risk_df = pd.DataFrame(risk_rows)
    review = pd.concat([risk_df, df], axis=1)

    need_review = review[
        (review["风险分"] > 0)
        | (~review["核心OK"].map(_as_bool))
        | (~review["严格OK"].map(_as_bool))
        | (review["判断来源"].isin(["unresolved", "line_match_weak", "market_reference", "material_plus_template", "craft_profile"]))
    ].copy()
    need_review = need_review.sort_values(
        by=["风险分", "置信度"],
        ascending=[False, True],
    )
    if top and top > 0:
        need_review = need_review.head(top)

    by_tag: Dict[str, int] = {}
    for tags in review["风险标签"]:
        for tag in str(tags).split("、"):
            if tag:
                by_tag[tag] = by_tag.get(tag, 0) + 1

    summary = {
        "audit_path": str(audit_path),
        "output_path": str(output_path),
        "rows": int(len(df)),
        "review_rows": int(len(need_review)),
        "top_risk": int(top),
        "by_tag": dict(sorted(by_tag.items(), key=lambda x: (-x[1], x[0]))),
        "by_source_review": need_review["判断来源"].value_counts().to_dict(),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as w:
        need_review.to_excel(w, sheet_name="待确认", index=False)
        pd.DataFrame(
            [{"指标": k, "值": json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v} for k, v in summary.items()]
        ).to_excel(w, sheet_name="汇总", index=False)
        src = need_review.groupby("判断来源").size().reset_index(name="待确认数量")
        src.sort_values("待确认数量", ascending=False).to_excel(w, sheet_name="按来源", index=False)

    if json_path:
        jp = Path(json_path)
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary
