# -*- coding: utf-8 -*-
"""精确 dump 金标准表头（openpyxl 原始值，含合并单元格）"""
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
import openpyxl
GOLD = r'd:\projects\cost-estimation\清单数据资料\AI学习清单\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价-20260818.xlsx'
wb = openpyxl.load_workbook(GOLD, data_only=True)
ws = wb['标准层户型85']
out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_header_exact_out.txt', 'w', encoding='utf-8')
out.write('merged cells:\n')
for mc in ws.merged_cells.ranges:
    out.write(f'  {mc}\n')
out.write('\n')
for i, row in enumerate(ws.iter_rows(min_row=1, max_row=9, max_col=17, values_only=True), 1):
    vals = ['' if v is None else str(v).replace('\n', '\\n')[:30] for v in row]
    out.write(f'r{i}: ' + ' | '.join(f'{j+1}:{vals[j]}' for j in range(17)) + '\n')
wb.close()
out.close()
print('done')
