# -*- coding: utf-8 -*-
"""调试金标准表头行识别"""
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
import pandas as pd
from src.ingest.detector import _score_header_row, _norm_header

GOLD = r'd:\projects\cost-estimation\清单数据资料\AI学习清单\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价-20260818.xlsx'
xl = pd.ExcelFile(GOLD)
df = xl.parse('标准层户型85', header=None)
out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_header_dbg_out.txt', 'w', encoding='utf-8')
for i in range(min(8, len(df))):
    row = df.iloc[i].tolist()
    vals = ['' if v is None or (isinstance(v,float) and pd.isna(v)) else _norm_header(v) for v in row[:17]]
    out.write(f'r{i+1}: {vals}\n')
    score, mapping = _score_header_row(row)
    out.write(f'    score={score} map={mapping}\n')
xl.close()
out.close()
print('done')
