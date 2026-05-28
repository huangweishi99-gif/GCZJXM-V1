"""乐晟招标清单成本分析摘要"""
import sqlite3

from src.export.cost_analysis import _ref_price
from src.knowledge.repository import KnowledgeRepository
from src.pricing.engine import PricingEngine

JOB_ID = 2
PROJECT_ID = 18

conn = sqlite3.connect("data/cost_pricing.db")
conn.row_factory = sqlite3.Row
engine = PricingEngine()
repo = KnowledgeRepository()

rows = conn.execute(
    """SELECT b.name, b.unit, b.quantity, b.feature, pl.match_level, pl.confidence
       FROM pricing_lines pl JOIN boq_lines b ON b.id=pl.boq_line_id
       WHERE pl.job_id=? ORDER BY b.quantity DESC""",
    (JOB_ID,),
).fetchall()

print("=== 工程量 Top10 ===")
for r in rows[:10]:
    cands = engine.search(r["name"], r["feature"] or "", r["unit"], top_n=1)
    best = cands[0] if cands else None
    if best:
        bs = f"{best['total_score']:.0%} -> {best['name'][:28]}"
    else:
        bs = "无候选"
    print(f"  {r['name'][:32]:32} {r['unit']:4} {float(r['quantity'] or 0):>10.2f}  {bs}")

keys = set((r["name"], r["unit"]) for r in rows)
print(f"\n清单行数: {len(rows)}  名称+单位去重: {len(keys)}")

ref_sum = 0.0
has_ref = 0
levels = {"A": 0, "B": 0, "C": 0, "D": 0}
for r in rows:
    levels[r["match_level"]] = levels.get(r["match_level"], 0) + 1
    cands = engine.search(r["name"], r["feature"] or "", r["unit"], top_n=1)
    if cands:
        p = _ref_price(repo, cands[0]["standard_item_id"])
        if p and r["quantity"]:
            ref_sum += p * float(r["quantity"])
            has_ref += 1

print(f"匹配等级: {levels}")
print(f"有历史参考单价: {has_ref}/{len(rows)}")
print(f"参考合价合计(候选1中位数×工程量): {ref_sum:,.2f} 元")

# 名称+单位+特征去重估算
from src.link.pricing_dedupe import dedupe_pricing_rows

raw = conn.execute(
    """SELECT b.id AS boq_line_id, b.seq, b.name, b.feature, b.unit, b.quantity,
              pl.match_level, pl.match_note,
              pl.material_main, pl.material_loss_rate, pl.material_aux,
              pl.labor, pl.machinery, pl.management, pl.profit, pl.tax,
              pl.cost_unit_price, pl.cost_amount, pl.unit_price
       FROM pricing_lines pl JOIN boq_lines b ON b.id=pl.boq_line_id
       WHERE pl.job_id=? ORDER BY b.id""",
    (JOB_ID,),
).fetchall()
items, _ = dedupe_pricing_rows([dict(r) for r in raw])
print(f"名称+单位+特征去重: {len(rows)}行 -> {len(items)}项")

conn.close()
