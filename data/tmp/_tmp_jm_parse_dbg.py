# -*- coding: utf-8 -*-
"""调试 parse_workbook 对金标准的解析"""
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
from src.ingest.parser import parse_workbook

GOLD = r'd:\projects\cost-estimation\清单数据资料\AI学习清单\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价-20260818.xlsx'
pw = parse_workbook(GOLD)
out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_parse_dbg_out.txt', 'w', encoding='utf-8')
out.write(f'format={pw.format_hint} sheets={pw.sheets}\n')
for ly in pw.layouts:
    out.write(f'  layout sheet={ly.sheet_name} header_row={ly.header_row} map={ly.column_map}\n')
out.write('\n')
for ln in pw.lines[:8]:
    out.write(f'[{ln.sheet_name}] "{ln.name}"\n')
    out.write(f'  主材={ln.material_main} 损耗={ln.material_loss_rate} 辅材={ln.material_aux} 人工={ln.labor} 机械={ln.machinery} 整价={ln.cost_unit_price} 报价={ln.unit_price} 管理={ln.management} 利润={ln.profit}\n')
    out.write(f'  feat={ln.feature[:50]}\n')
out.close()
print(f'lines={len(pw.lines)} layouts={list(pw.sheet_layouts.keys()) if isinstance(pw.sheet_layouts, dict) else pw.sheet_layouts}')
