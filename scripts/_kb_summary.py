import sqlite3
from pathlib import Path

conn = sqlite3.connect("data/cost_pricing.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """SELECT p.id, p.name, p.city, p.price_tier, p.source_file,
              (SELECT COUNT(*) FROM cost_records cr
               WHERE cr.source_project_id = p.id) AS costs
       FROM projects p WHERE project_type='historical' ORDER BY p.id"""
).fetchall()
print("=== AI学习清单 9个项目归类 ===")
for r in rows:
    fn = Path(r["source_file"] or "").name
    print(
        f"{r['id']}. [{r['city'] or '通用'}·{r['price_tier']}] "
        f"{fn} → {r['costs']}条成本"
    )
st = conn.execute(
    "SELECT COUNT(*) FROM line_price_facts"
).fetchone()[0]
mf = conn.execute(
    "SELECT COUNT(*) FROM material_price_facts"
).fetchone()[0]
print(f"\n清单项价库: {st}  材料规格价库: {mf}")
mats = conn.execute(
    """SELECT city, price_tier, COUNT(*) c FROM material_price_facts
       GROUP BY city, price_tier ORDER BY city, price_tier"""
).fetchall()
print("材料价库按城市×档位:")
for m in mats:
    print(f"  {m['city'] or '通用'} / {m['price_tier']}: {m['c']}种")
conn.close()
