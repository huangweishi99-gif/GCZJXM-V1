# -*- coding: utf-8 -*-
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
import openpyxl
NEW = r'd:\projects\cost-estimation\data\exports\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价_成本填写.xlsx'
wb = openpyxl.load_workbook(NEW, data_only=True, read_only=True)
ws = wb['标准层户型85']
out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_new_full_out.txt', 'w', encoding='utf-8')
for i, row in enumerate(ws.iter_rows(min_row=7, max_row=16, values_only=True), 7):
    vals = ['' if v is None else str(v).replace('\n', '|')[:14] for v in row[:25]]
    out.write(f'L{i}: ' + ' | '.join(f'{j+1}:{vals[j]}' for j in range(25)) + '\n')
wb.close()
out.close()
print('done')
