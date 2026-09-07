# -*- coding: utf-8 -*-
"""查 line_price_facts 与 standard_items 中 楼地面/涂料 相关项"""
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
from src.db.database import get_connection

conn = get_connection()
out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_fact_check_out.txt', 'w', encoding='utf-8')
out.write('== standard_items 含"楼地面" ==\n')
for r in conn.execute("SELECT id, name_norm, feature_norm, unit_norm, sample_count FROM standard_items WHERE name_norm LIKE '%楼地面%' LIMIT 15"):
    out.write(f'  sid={r["id"]} "{r["name_norm"]}" unit={r["unit_norm"]} n={r["sample_count"]} feat={str(r["feature_norm"])[:40]}\n')
out.write('\n== standard_items 含"内墙涂料" ==\n')
for r in conn.execute("SELECT id, name_norm, feature_norm, unit_norm, sample_count FROM standard_items WHERE name_norm LIKE '%内墙涂料%' OR name_norm LIKE '%涂料%' LIMIT 10"):
    out.write(f'  sid={r["id"]} "{r["name_norm"]}" n={r["sample_count"]} feat={str(r["feature_norm"])[:40]}\n')
out.write('\n== cost_records(江门项目) 楼地面 ==\n')
for r in conn.execute("SELECT cr.id, cr.standard_item_id, cr.material_main, cr.material_loss_rate, cr.material_aux, cr.labor, cr.machinery, cr.cost_unit_price FROM cost_records cr JOIN projects p ON p.id=cr.source_project_id WHERE p.name LIKE '%江门%' AND cr.standard_item_id IN (SELECT id FROM standard_items WHERE name_norm LIKE '%楼地面%') LIMIT 10"):
    out.write(f'  rec={r["id"]} sid={r["standard_item_id"]} 主材={r["material_main"]} 损耗={r["material_loss_rate"]} 辅材={r["material_aux"]} 人工={r["labor"]} 机械={r["machinery"]} 整价={r["cost_unit_price"]}\n')
out.write('\n== line_price_facts 所有 楼地面 相关 ==\n')
for r in conn.execute("SELECT lpf.*, si.name_norm FROM line_price_facts lpf JOIN standard_items si ON si.id=lpf.standard_item_id WHERE si.name_norm LIKE '%楼地面%' LIMIT 15"):
    out.write(f'  sid={r["standard_item_id"]} "{r["name_norm"]}" {r["city"]}/{r["price_tier"]} n={r["sample_count"]} 主材={r["material_main"]} 损耗={r["material_loss_rate"]} 辅材={r["material_aux"]} 人工={r["labor"]} 机械={r["machinery"]} 整价={r["cost_unit_price"]}\n')
conn.close()
out.close()
print('done')
