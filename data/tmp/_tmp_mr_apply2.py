# -*- coding: utf-8 -*-
"""第二轮修正 market_reference 表值（净收益明确的）"""
import io
import json
import shutil
from pathlib import Path

CFG = Path(r'd:\projects\cost-estimation\config\market_reference_prices.json')
LOG = Path(r'd:\projects\cost-estimation\data\tmp\_tmp_mr_apply2_out.txt')

UPDATES = {
    'zh_metal_trim_mt': {'material_main': 2650.0, 'labor': 35.0},   # MT置物架
    'cleaning_delivery': {'material_main': 10.0, 'labor': 0.0},     # 保洁交付
    'waste_bin': {'material_main': 54.0},                            # 垃圾箱 补主材
    'demolition_generic': {'labor': 186.08},                         # 拆除通用人工
    'tile_wall_adhesive_ct': {'material_main': 137.46},              # CT墙砖
    'zh_pivot_door': {'material_main': 1750.0},                      # 转轴门
    'ac_outdoor_unit': {'material_main': 26343.36},                  # 多联式室外机
    'putty_hang_waterproof': {'material_main': 3.50, 'labor': 20.0}, # 耐水腻子（微利+2）
    'tile_600x1200_floor': {'material_main': 141.28},                # 600x1200地砖
}

cfg = json.loads(CFG.read_text(encoding='utf-8'))
rules = {r['id']: r for r in cfg['rules']}

buf = []
changed = 0
for rid, fields in UPDATES.items():
    r = rules.get(rid)
    if r is None:
        buf.append('!! 未找到规则: %s' % rid)
        continue
    for f, v in fields.items():
        old = r.get(f, 0)
        if abs(old - v) > 1e-9:
            r[f] = v
            buf.append('%-32s %-14s %s -> %s' % (rid, f, old, v))
            changed += 1

CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
buf.append('\n共修改 %d 个字段' % changed)
LOG.write_text('\n'.join(buf), encoding='utf-8')
print('done, changed=%d' % changed)
