# -*- coding: utf-8 -*-
"""查数据库项目列表"""
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
from src.db.database import get_connection

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT id, name, city, price_tier, source_file FROM projects ORDER BY id")
rows = cur.fetchall()
out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_db_out.txt', 'w', encoding='utf-8')
for r in rows:
    out.write(f'{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]}\n')
cur.execute("SELECT COUNT(*) FROM cost_records")
out.write(f'cost_records total: {cur.fetchone()[0]}\n')
cur.execute("SELECT source_project_id, COUNT(*) FROM cost_records GROUP BY source_project_id")
for r in cur.fetchall():
    out.write(f'  project {r[0]}: {r[1]} records\n')
conn.close()
out.close()
print('done')
