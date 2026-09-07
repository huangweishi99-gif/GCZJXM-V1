# -*- coding: utf-8 -*-
"""分析 audit 明细中 market_reference 失败行的偏差模式（Part2）"""
import io
import pandas as pd

AUDIT = r'd:\projects\cost-estimation\data\exports\抽检报告_人材机判断.xlsx'
OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_mr_analyze_out.txt'

df = pd.read_excel(AUDIT, sheet_name='明细')

# 布尔列转换
for c in ['主材OK', '人工OK', '合计OK', '核心OK', '严格OK', '可自动填']:
    df[c] = df[c].map(lambda v: str(v).strip().lower() in ('true', '1', 'yes', 'y'))

mr = df[(df['判断来源'] == 'market_reference') & (~df['核心OK'])].copy()
buf = ['market_reference 失败行数: %d' % len(mr)]

# 计算相对偏差
mr['主材_偏差'] = (mr['判_主材'] - mr['实_主材'])
mr['人工_偏差'] = (mr['判_人工'] - mr['实_人工'])

# 1. 主材偏差最严重的 Top 30（按偏差绝对值）
buf.append('\n=== 主材偏差 Top 40（判-实，绝对值大）===')
top = mr.reindex(mr['主材_偏差'].abs().sort_values(ascending=False).index).head(40)
for _, r in top.iterrows():
    buf.append('%s | 主材 判%.2f/实%.2f | 人工 判%.2f/实%.2f | %s' % (
        r['单位'], r['判_主材'], r['实_主材'], r['判_人工'], r['实_人工'], str(r['项目名称'])[:60]))

# 2. 人工偏差最严重的 Top 40
buf.append('\n=== 人工偏差 Top 40（判-实，绝对值大）===')
top = mr.reindex(mr['人工_偏差'].abs().sort_values(ascending=False).index).head(40)
for _, r in top.iterrows():
    buf.append('%s | 主材 判%.2f/实%.2f | 人工 判%.2f/实%.2f | %s' % (
        r['单位'], r['判_主材'], r['实_主材'], r['判_人工'], r['实_人工'], str(r['项目名称'])[:60]))

# 3. 相同名称聚合统计（同名多次出现时判 vs 实是否一致）
buf.append('\n=== 同名失败聚合（出现>=2次）===' )
name_g = mr.groupby('项目名称').agg(
    n=('record_id', 'count'),
    判主材=('判_主材', 'first'),
    实主材=('实_主材', 'first'),
    判人工=('判_人工', 'first'),
    实人工=('实_人工', 'first'),
).reset_index()
name_g = name_g[name_g['n'] >= 2].sort_values('n', ascending=False)
for _, r in name_g.head(40).iterrows():
    buf.append('x%d | 主材 判%.2f/实%.2f | 人工 判%.2f/实%.2f | %s' % (
        r['n'], r['判主材'], r['实主材'], r['判人工'], r['实人工'], str(r['项目名称'])[:70]))

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('done')
