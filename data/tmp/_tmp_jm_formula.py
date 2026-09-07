# -*- coding: utf-8 -*-
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
import openpyxl
NEW = r'd:\projects\cost-estimation\data\exports\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价_成本填写.xlsx'
wb = openpyxl.load_workbook(NEW, data_only=False)
ws = wb['标准层户型85']
out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_formula_out.txt', 'w', encoding='utf-8')
for i, row in enumerate(ws.iter_rows(min_row=8, max_row=12), 8):
    out.write(f'=== L{i} ===\n')
    for j, cell in enumerate(row, 1):
        if cell.value is not None and j <= 26:
            out.write(f'  c{j} [{cell.coordinate}]: {str(cell.value)[:90]}\n')
wb.close()
out.close()
print('done')
