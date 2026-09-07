# -*- coding: utf-8 -*-
"""新版deliver vs 金标准：按行对齐对比主材/人工/辅材/损耗"""
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
import openpyxl

GOLD = r'd:\projects\cost-estimation\清单数据资料\AI学习清单\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价-20260818.xlsx'
NEW = r'd:\projects\cost-estimation\data\exports\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价_成本填写.xlsx'

def load(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb['标准层户型85']
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return rows

g = load(GOLD)
n = load(NEW)

def v(x):
    if x is None or x == '':
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None

def rel(a, b):
    if a is None or b is None:
        return None
    if b == 0:
        return 0.0 if a == 0 else None
    return abs(a - b) / b

# 金标准: I=8人工 J=9辅材 K=10主材 L=11损耗
# 新版:   c20=19主材 c21=20损耗 c22=21人工 c23=22辅材
g_rows, n_rows = [], []
sect = ''
for i, r in enumerate(g):
    name = str(r[2] or '').strip()
    if not name:
        continue
    if r[1] and str(r[1]).startswith('一'):
        sect = name
        continue
    if v(r[8]) is None:
        continue
    g_rows.append((i, sect, name, dict(main=v(r[10]), loss=v(r[11]), labor=v(r[8]), aux=v(r[9]))))
sect2 = ''
for i, r in enumerate(n):
    name = str(r[2] or '').strip()
    if not name:
        continue
    if r[1] and str(r[1]).startswith('一'):
        sect2 = name
        continue
    if v(r[19]) is None and v(r[21]) is None:
        continue
    n_rows.append((i, sect2, name, dict(main=v(r[19]), loss=v(r[20]), labor=v(r[21]), aux=v(r[22]))))

out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_final_cmp_out.txt', 'w', encoding='utf-8')
out.write(f'金标准 {len(g_rows)} 行 vs 新版 {len(n_rows)} 行\n\n')
# 按顺序 zip（两文件行结构一致）
from itertools import zip_longest
results = []
for gi, (gr, nr) in enumerate(zip_longest(g_rows, n_rows)):
    if gr is None or nr is None:
        continue
    (i1, s1, nm1, gv), (i2, s2, nm2, nv) = gr, nr
    ok = {}
    for key, label in [('main', '主材'), ('labor', '人工'), ('aux', '辅材'), ('loss', '损耗')]:
        ga, na = gv[key], nv[key]
        r = rel(na, ga)
        ok[key] = r is not None and r <= 0.20
    all_ok = ok['main'] and ok['labor'] and ok['aux'] and ok['loss']
    results.append((i1, s1, nm1, gv, nv, ok, all_ok))

for key, label in [('main', '主材'), ('labor', '人工'), ('aux', '辅材'), ('loss', '损耗')]:
    tot = len(results)
    okn = sum(1 for r in results if r[5][key])
    out.write(f'## {label}: OK {okn}/{tot} ({okn/max(tot,1):.0%})\n')
all_ok_n = sum(1 for r in results if r[6])
out.write(f'\n## 四项全OK: {all_ok_n}/{len(results)} ({all_ok_n/max(len(results),1):.0%})\n\n')
out.write('== 失败明细 ==\n')
for i1, s1, nm1, gv, nv, ok, all_ok in results:
    if all_ok:
        continue
    parts = []
    for key, label in [('main', '主材'), ('labor', '人工'), ('aux', '辅材'), ('loss', '损耗')]:
        ga, na = gv[key], nv[key]
        parts.append(f'{label}:实{ga}/判{na}')
    out.write(f'L{i1+1} [{s1}] {nm1[:18]} | ' + ' '.join(parts) + '\n')
out.close()
print(f'done gold={len(g_rows)} new={len(n_rows)} all_ok={all_ok_n}')
