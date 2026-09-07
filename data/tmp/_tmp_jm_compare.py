# -*- coding: utf-8 -*-
"""江门项目：正确价格 vs 我的成本填写 对比分析"""
import io, re, sys
from pathlib import Path
sys.path.insert(0, r'd:\projects\cost-estimation')
import openpyxl

GOLD = r'd:\projects\cost-estimation\清单数据资料\AI学习清单\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价-20260818.xlsx'
MINE = r'd:\projects\cost-estimation\data\exports\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价_成本填写.xlsx'

def load(sheet, path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet]
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append(list(row))
    wb.close()
    return rows

g = load('标准层户型85', GOLD)
m = load('标准层户型85', MINE)

out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_compare_out.txt', 'w', encoding='utf-8')

def v(x):
    if x is None or x == '':
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None

def rel(a, b):
    """相对偏差；基准为 0 时按实际值计"""
    if a is None or b is None:
        return None
    if b == 0:
        return 0.0 if a == 0 else None
    return abs(a - b) / b

# 列索引（0-based）
# A编号 B编码 C名称 D特征 E索引 F采购 G单位 H工程量 I人工 J辅材机械 K主材单价 L损耗率 M主材费 N综合费 O综合单价
idx = dict(name=2, feat=3, unit=6, qty=7, labor=8, aux=9, main_p=10, loss=11, main_f=12, fee=13, total=14)

rows_out = []
detail = []
sect = ''
for i, (gr, mr) in enumerate(zip(g, m)):
    name_g, name_m = gr[idx['name']], mr[idx['name']]
    nm = (name_g if name_g else name_m) or ''
    nm = str(nm).strip()
    if not nm:
        continue
    # section 行：编码为空或非数字行首
    code = gr[idx['name'] - 1]
    if code and str(code).startswith('一'):
        sect = nm
        continue
    # 数据行需要人工费
    g_labor = v(gr[idx['labor']])
    m_labor = v(mr[idx['labor']])
    if g_labor is None and m_labor is None:
        continue
    gv = dict(labor=g_labor, aux=v(gr[idx['aux']]), main_p=v(gr[idx['main_p']]),
              loss=v(gr[idx['loss']]), main_f=v(gr[idx['main_f']]),
              fee=v(gr[idx['fee']]), total=v(gr[idx['total']]))
    mv = dict(labor=m_labor, aux=v(mr[idx['aux']]), main_p=v(mr[idx['main_p']]),
              loss=v(mr[idx['loss']]))
    feat = str(gr[idx['feat']] or mr[idx['feat']] or '')[:60]
    rows_out.append((i, sect, nm, feat, gv, mv))

# 汇总统计
out.write(f'数据行总数: {len(rows_out)}\n')
out.write('=' * 120 + '\n')

def stat_col(key, label):
    n_ok = n_fail = n_no = n_total = 0
    bad = []
    for i, sect, nm, feat, gv, mv in rows_out:
        ga, ma = gv[key], mv.get(key)
        if ga is None:
            continue
        n_total += 1
        if ma is None:
            n_no += 1
            bad.append((i, sect, nm, ga, ma, '无判值'))
            continue
        r = rel(ma, ga)
        if r is None:
            n_fail += 1
            bad.append((i, sect, nm, ga, ma, f'abs差={abs(ma-ga):.2f}'))
        elif r <= 0.20:
            n_ok += 1
        else:
            n_fail += 1
            bad.append((i, sect, nm, ga, ma, f'rel={r:.0%} abs差={abs(ma-ga):.2f}'))
    out.write(f'\n## {label}: 总{n_total} 一致≤20% {n_ok} ({n_ok/max(n_total,1):.0%}) 偏差>20% {n_fail} 缺判 {n_no}\n')
    for b in bad[:40]:
        out.write(f'  L{b[0]+1} [{b[1]}] {b[2][:26]} 实{b[3]} 判{b[4]} {b[5]}\n')
    if len(bad) > 40:
        out.write(f'  ... 共 {len(bad)} 行偏差\n')

for key, label in [('main_p', '主材单价e'), ('labor', '人工费b'), ('aux', '辅材+机械c'), ('loss', '损耗率f')]:
    stat_col(key, label)

out.close()
print(f'done rows={len(rows_out)}')
