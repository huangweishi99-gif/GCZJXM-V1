# -*- coding: utf-8 -*-
"""分析 mep_install_profile 失败行的偏差模式（按判值分组=函数分支）"""
import io
import json
import statistics
import sys
from pathlib import Path
import pandas as pd

AUDIT = r'd:\projects\cost-estimation\data\exports\抽检报告_人材机判断.xlsx'
OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_mep_analyze_out.txt'

df = pd.read_excel(AUDIT, sheet_name='明细')
for c in ['核心OK']:
    df[c] = df[c].map(lambda v: str(v).strip().lower() in ('true', '1', 'yes', 'y'))
mr = df[df['判断来源'] == 'mep_install_profile'].copy()

buf = ['mep_install_profile 总行数: %d, 成功: %d, 失败: %d' % (
    len(mr), mr['核心OK'].sum(), (~mr['核心OK']).sum())]

fail = mr[~mr['核心OK']].copy()
fail['判组合'] = fail['判_主材'].round(2).astype(str) + '/' + fail['判_人工'].round(2).astype(str)

# 按判值组合分组（同判值≈同函数分支）
buf.append('\n=== 按判值分组（失败行，n>=3）===')
groups = []
for key, g in fail.groupby('判组合'):
    n = len(g)
    if n < 3:
        continue
    em = statistics.median(g['实_主材'])
    el = statistics.median(g['实_人工'])
    # 偏差
    pm = g['判_主材'].iloc[0]
    pl = g['判_人工'].iloc[0]
    names = g['项目名称'].head(3).tolist()
    units = g['单位'].value_counts().head(2).to_dict()
    groups.append((key, n, pm, em, pl, el, names, units))

groups.sort(key=lambda x: -x[1])
for key, n, pm, em, pl, el, names, units in groups:
    buf.append('\n判%s x%d | 实主材中位%.2f(判%.2f) 实人工中位%.2f(判%.2f) | 单位%s' % (
        key, n, em, pm, el, pl, units))
    for nm in names:
        buf.append('   %s' % str(nm)[:70])

# 也看看"判组合"里成功+失败 混合的情况：哪些分支成功率高
buf.append('\n=== 分支成功率（按判值分组，全部行）===')
allg = {}
for _, r in mr.iterrows():
    key = '%.2f/%.2f' % (r['判_主材'], r['判_人工'])
    d = allg.setdefault(key, {'n': 0, 'ok': 0})
    d['n'] += 1
    d['ok'] += int(bool(r['核心OK']))
rows = [(k, v['n'], v['ok']) for k, v in allg.items() if v['n'] >= 5]
rows.sort(key=lambda x: -x[2] / x[1])
buf.append('成功率最高 Top15:')
for k, n, ok in rows[:15]:
    buf.append('  %-16s 总%d OK%d (%.0f%%)' % (k, n, ok, 100 * ok / n))
buf.append('成功率最低 Top20:')
for k, n, ok in rows[-20:]:
    buf.append('  %-16s 总%d OK%d (%.0f%%)' % (k, n, ok, 100 * ok / n))

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('done')
