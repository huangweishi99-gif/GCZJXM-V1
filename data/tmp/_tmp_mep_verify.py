# -*- coding: utf-8 -*-
"""输出 5.57/9.12 等可疑失败行的完整字段"""
import io
import pandas as pd

AUDIT = r'd:\projects\cost-estimation\data\exports\抽检报告_人材机判断.xlsx'
OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_mep_verify_out.txt'

df = pd.read_excel(AUDIT, sheet_name='明细')

buf = []
for pm, pl in [('5.57', '9.12'), ('2.92', '2.20'), ('25.0', '29.8'), ('20.0', '18.0'), ('30.0', '12.2'), ('85.0', '48.0'), ('550.0', '90.0'), ('15.0', '10.0')]:
    mask = (df['判_主材'].round(2).astype(str) == pm) & (df['判_人工'].round(2).astype(str) == pl)
    sub = df[mask]
    buf.append('=' * 70)
    buf.append('判 %s/%s 共%d行' % (pm, pl, len(sub)))
    for _, r in sub.head(8).iterrows():
        buf.append('  名称=%s' % str(r['项目名称'])[:45])
        buf.append('    实主材=%.2f 判主材=%.2f 主材OK=%s | 实人工=%.2f 判人工=%.2f 人工OK=%s | 核心OK=%s 可自动填=%s 来源=%s 置信=%.3f' % (
            r['实_主材'], r['判_主材'], r['主材OK'], r['实_人工'], r['判_人工'], r['人工OK'],
            r['核心OK'], r['可自动填'], r['判断来源'], r['置信度']))

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('done')
