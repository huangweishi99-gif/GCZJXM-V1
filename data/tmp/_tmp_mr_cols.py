# -*- coding: utf-8 -*-
"""查看 audit 明细的完整列名"""
import io
import pandas as pd

AUDIT = r'd:\projects\cost-estimation\data\exports\抽检报告_人材机判断.xlsx'
OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_mr_cols_out.txt'

xl = pd.ExcelFile(AUDIT)
buf = ['sheets: %s' % xl.sheet_names]
df = xl.parse(xl.sheet_names[0])
buf.append('sheet0 列: %s' % list(df.columns))
if len(xl.sheet_names) > 1:
    df2 = xl.parse(xl.sheet_names[1])
    buf.append('sheet1 列: %s' % list(df2.columns))

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('done')
