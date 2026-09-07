# -*- coding: utf-8 -*-
"""验证吸顶灯/平板灯修复"""
import io
import sys

sys.path.insert(0, r'd:\projects\cost-estimation')
from src.db.database import get_connection
from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.pricing.component_judge import judge_line_components
from src.pricing.engine import PricingEngine
from src.pricing.judge_audit import _component_ok, load_audit_samples

OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_lighting_verify_out.txt'

conn = get_connection()
try:
    samples = load_audit_samples(conn)
finally:
    conn.close()

KW = ("吸顶灯", "平板灯")
focus = [s for s in samples if any(k in (s.name or "") for k in KW) or any(k in (s.feature or "") for k in KW)]
print(f"吸顶灯/平板灯样本: {len(focus)}")

repo = KnowledgeRepository()
engine = PricingEngine()

lines = []
ok_n = 0
for s in focus:
    ctx = PricingContext(city=s.city, price_tier=s.price_tier)
    j = judge_line_components(
        s.name, s.feature, s.unit, engine, repo, ctx=ctx,
        exclude_standard_item_id=s.standard_item_id,
    )
    if j.source != "lighting_fixture_code":
        lines.append(f"[SKIP src={j.source}] {s.name}")
        continue
    pred = j.as_components()
    am = s.actual.get("material_main") or 0
    al = s.actual.get("labor") or 0
    main_ok = _component_ok(pred.get("material_main") or 0, am)
    labor_ok = _component_ok(pred.get("labor") or 0, al)
    core_ok = (main_ok if am > 0.01 else True) and (labor_ok if al > 0.01 else True)
    ok_n += 1 if core_ok else 0
    tag = "OK  " if core_ok else "FAIL"
    lines.append(f"[{tag}] {s.name} | {s.city}/{s.price_tier} | 判:{pred.get('material_main')}/{pred.get('labor')} 实:{am}/{al}")

lines.insert(0, f"lighting 吸顶/平板 OK {ok_n}/{sum(1 for l in lines if l.startswith('['))}")
with io.open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\n".join(lines))
