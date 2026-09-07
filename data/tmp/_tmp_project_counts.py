# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'd:\projects\cost-estimation')
from src.db.database import get_connection
conn = get_connection()
rows = conn.execute(
    """SELECT p.id, p.name, COUNT(cr.id) AS n
       FROM projects p LEFT JOIN cost_records cr ON cr.source_project_id=p.id
       GROUP BY p.id ORDER BY n DESC"""
).fetchall()
for r in rows:
    print(f"{r['id']:5d}  n={r['n']:6d}  {r['name'] or ''}")
