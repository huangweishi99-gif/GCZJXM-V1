# -*- coding: utf-8 -*-
"""临时：提取 mep_install_profile 样本诊断失败形态。"""
import io, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from collections import Counter

from src.db.database import get_connection
from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.pricing.engine import PricingEngine
from src.pricing.judge_audit import load_audit_samples, _evaluate_row
from src.pricing.component_judge import judge_line_components
from src.pricing.cost_basis import get_net_divisor

ROOT = Path(__file__).resolve().parents[2]
conn = get_connection()
repo = KnowledgeRepository()
engine = PricingEngine()
net_divisor = get_net_divisor(repo.settings.get("pricing", {}))

samples = load_audit_samples(conn)
sim_keys = ("附件2-1", "附件2-2", "模拟工程量", "框架清单")
fee_keys = ("安全文明施工费", "安全生产责任险", "材料搬运费", "综合专业设计出图", "总承包服务费", "现场成品保护")
samples = [s for s in samples if not any(k in s.project_name for k in sim_keys)]
samples = [s for s in samples if not any(k in s.name for k in fee_keys)]

def r2(v):
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0

rows = []
for i, s in enumerate(samples, 1):
    ctx = PricingContext(city=s.city, price_tier=s.price_tier)
    j = judge_line_components(s.name, s.feature, s.unit, engine, repo, ctx=ctx,
                              exclude_standard_item_id=s.standard_item_id)
    if j.source != "mep_install_profile":
        continue
    r = _evaluate_row(s, j, rel_tol=0.20, abs_tol=5.0, total_rel_tol=0.15, net_divisor=net_divisor)
    a = s.actual or {}
    rows.append({
        "record_id": s.record_id, "project_id": s.project_id, "name": s.name,
        "feature": s.feature, "unit": s.unit, "city": s.city, "tier": s.price_tier,
        "core_ok": bool(r.core_ok), "auto": bool(r.auto_fill_ok),
        "conf": r2(j.confidence), "craft": getattr(j, "craft_type", ""),
        "a_main": r2(a.get("material_main")), "a_labor": r2(a.get("labor")),
        "p_main": r2(r.pred.get("material_main")), "p_labor": r2(r.pred.get("labor")),
        "notes": j.notes[-1] if j.notes else "",
    })
    if i % 2000 == 0:
        print(f"  {i}/{len(samples)}", flush=True)

(ROOT / "data" / "tmp" / "_mep_rows.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\nmep_install_profile 样本 {len(rows)}")
ok = [x for x in rows if x["core_ok"]]
bad = [x for x in rows if not x["core_ok"]]
print(f"core_ok: {len(ok)}/{len(rows)} = {len(ok)/max(len(rows),1):.3f}  auto:{sum(x['auto'] for x in rows)}")

def seg(x):
    n = re.split(r"[，,、；;：:\s（(【]", x["name"])[0]
    return n[:12]

print("\n=== 失败样本 top150（按名首个分段）===")
for x in bad[:150]:
    flag = "A" if x["auto"] else " "
    print(f"  [{flag}] {x['record_id']:>5} {x['name'][:34]:<34} | {x['a_main']:>9.1f}->{x['p_main']:>8.1f} 人 {x['a_labor']:>7.1f}->{x['p_labor']:>7.1f} | {x['notes'][:26]}")
