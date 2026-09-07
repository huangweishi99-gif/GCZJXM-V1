# -*- coding: utf-8 -*-
"""dump lighting_fixture_code 失败行"""
import io
import sys

sys.path.insert(0, r'd:\projects\cost-estimation')
from src.db.database import get_connection
from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.pricing.component_judge import judge_line_components
from src.pricing.engine import PricingEngine
from src.pricing.judge_audit import _component_ok, load_audit_samples

OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_lighting_dump_out.txt'

conn = get_connection()
try:
    samples = load_audit_samples(conn)
finally:
    conn.close()

KW = ("灯", "灯具", "筒灯", "射灯", "吸顶", "格栅", "光源")
focus = [s for s in samples if any(k in (s.name or "") for k in KW)]

repo = KnowledgeRepository()
engine = PricingEngine()

lines = []
for s in focus:
    ctx = PricingContext(city=s.city, price_tier=s.price_tier)
    j = judge_line_components(
        s.name, s.feature, s.unit, engine, repo, ctx=ctx,
        exclude_standard_item_id=s.standard_item_id,
    )
    if j.source != "lighting_fixture_code":
        continue
    pred = j.as_components()
    am = s.actual.get("material_main") or 0
    al = s.actual.get("labor") or 0
    main_ok = _component_ok(pred.get("material_main") or 0, am)
    labor_ok = _component_ok(pred.get("labor") or 0, al)
    core_ok = (main_ok if am > 0.01 else True) and (labor_ok if al > 0.01 else True)
    tag = "OK  " if core_ok else "FAIL"
    lines.append(f"[{tag}] {s.name} | {s.unit} | {s.city}/{s.price_tier} | id={s.record_id}")
    lines.append(f"   特征: {(s.feature or '')[:100]}")
    lines.append(f"   判: 主材{pred.get('material_main')} 人工{pred.get('labor')} 辅材{pred.get('material_aux')} 机械{pred.get('machinery')}")
    lines.append(f"   实: 主材{am} 人工{al} 辅材{s.actual.get('material_aux')} 机械{s.actual.get('machinery')}")

with io.open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"lighting_fixture_code 行数: {len(lines)//4} -> {OUT}")
