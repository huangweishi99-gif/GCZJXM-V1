# -*- coding: utf-8 -*-
"""聚焦验证：开关/插座类样本 pred vs actual（三联/双联分支校准效果）"""
import io
import sys
from pathlib import Path

sys.path.insert(0, r'd:\projects\cost-estimation')
from src.db.database import get_connection
from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.pricing.component_judge import judge_line_components
from src.pricing.engine import PricingEngine
from src.pricing.judge_audit import _component_ok, load_audit_samples

OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_mep_switch_verify_out.txt'

conn = get_connection()
try:
    samples = load_audit_samples(conn)
finally:
    conn.close()

repo = KnowledgeRepository()
engine = PricingEngine()

kw = ("开关", "插座")
focus = [s for s in samples if any(k in (s.name or "") for k in kw) or any(k in (s.feature or "") for k in kw)]
print(f"开关/插座样本数: {len(focus)}")

buf = []
for s in focus:
    ctx = PricingContext(city=s.city, price_tier=s.price_tier)
    j = judge_line_components(
        s.name, s.feature, s.unit, engine, repo, ctx=ctx,
        exclude_standard_item_id=s.standard_item_id,
    )
    pred = j.as_components()
    main_ok = _component_ok(pred.get("material_main") or 0, s.actual.get("material_main") or 0)
    labor_ok = _component_ok(pred.get("labor") or 0, s.actual.get("labor") or 0)
    am = s.actual.get("material_main") or 0
    al = s.actual.get("labor") or 0
    core_ok = (main_ok if am > 0.01 else True) and (labor_ok if al > 0.01 else True)
    buf.append({
        "name": (s.name or "")[:40],
        "unit": s.unit,
        "src": j.source,
        "pred_main": round(pred.get("material_main") or 0, 2),
        "act_main": round(am, 2),
        "main_ok": main_ok,
        "pred_labor": round(pred.get("labor") or 0, 2),
        "act_labor": round(al, 2),
        "labor_ok": labor_ok,
        "core_ok": core_ok,
    })

lines = [f"开关/插座样本总数: {len(buf)}"]
for tag in ("三联", "双联", "单联"):
    sub = [r for r in buf if tag in r["name"]]
    if not sub:
        continue
    ok = sum(1 for r in sub if r["core_ok"])
    lines.append(f"\n=== 名称含[{tag}]: {len(sub)} 行, core OK {ok} ({100*ok/len(sub):.0f}%) ===")
    for r in sub:
        lines.append("  %-42s %-3s src=%-22s 主材 %6.2f/%6.2f %s | 人工 %6.2f/%6.2f %s | %s" % (
            r["name"], r["unit"], r["src"], r["pred_main"], r["act_main"], "OK" if r["main_ok"] else "x",
            r["pred_labor"], r["act_labor"], "OK" if r["labor_ok"] else "x",
            "CORE_OK" if r["core_ok"] else "FAIL"))

ok_all = sum(1 for r in buf if r["core_ok"])
lines.append(f"\n=== 全部开关/插座: {len(buf)} 行, core OK {ok_all} ({100*ok_all/max(1,len(buf)):.0f}%) ===")

with io.open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"done -> {OUT}")
