# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'd:\projects\cost-estimation')
from src.db.database import get_connection
conn = get_connection()
rows = conn.execute(
    "SELECT id, name, city FROM projects ORDER BY id"
).fetchall()
for r in rows:
    print(f"{r['id']:5d}  {r['name'] or ''}  {r['city'] or ''}")
