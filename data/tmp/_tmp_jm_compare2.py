# -*- coding: utf-8 -*-
"""对比 改进版export vs 金标准；同时保留 OLD 版对比"""
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
import openpyxl

GOLD = r'd:\projects\cost-estimation\清单数据资料\AI学习清单\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价-20260818.xlsx'
NEW = r'd:\projects\cost-estimation\data\exports\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价_成本填写.xlsx'
OLD = r'd:\projects\cost-estimation\data\exports\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价_成本填写_OLD.xlsx'

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

idx = dict(name=2, feat=3, labor=8, aux=9, main_p=10, loss=11, main_f=12, fee=13, total=14)

def collect(rows):
    data = []
    sect = ''
    for i, r in enumerate(rows):
        nm = str(r[idx['name']] or '').strip()
        code = r[idx['name'] - 1]
        if not nm:
            continue
        if code and str(code).startswith('一'):
            sect = nm
            continue
        la = v(r[idx['labor']])
        if la is None:
            continue
        data.append((i, sect, nm, dict(
            labor=la, aux=v(r[idx['aux']]), main_p=v(r[idx['main_p']]),
            loss=v(r[idx['loss']]), main_f=v(r[idx['main_f']]), total=v(r[idx['total']]))))
    return data

gd = collect(g)

def compare(mine_rows, label, out):
    md = collect(mine_rows)
    out.write(f'\n{"="*90}\n{label}\n{"="*90}\n')
    for key, klabel in [('main_p', '主材单价e'), ('labor', '人工费b'), ('aux', '辅材+机械c'), ('loss', '损耗率f')]:
        n_ok = n_fail = n_no = n_total = 0
        bad = []
        for (gi, sect, nm, gv), (mi, _, nm2, mv) in zip(gd, md):
            ga = gv[key]
            if ga is None:
                continue
            n_total += 1
            ma = mv.get(key)
            if ma is None:
                n_no += 1
                bad.append((gi, sect, nm, ga, ma, '无判值'))
                continue
            r = rel(ma, ga)
            if r is None:
                n_fail += 1
                bad.append((gi, sect, nm, ga, ma, f'abs={abs(ma-ga):.2f}'))
            elif r <= 0.20:
                n_ok += 1
            else:
                n_fail += 1
                bad.append((gi, sect, nm, ga, ma, f'rel={r:.0%}'))
        out.write(f'## {klabel}: 总{n_total} OK≤20% {n_ok} ({n_ok/max(n_total,1):.0%}) FAIL {n_fail} 缺 {n_no}\n')
        for b in bad[:25]:
            out.write(f'  L{b[0]+1} [{b[1]}] {str(b[2])[:24]} 实{b[3]} 判{b[4]} {b[5]}\n')
        if len(bad) > 25:
            out.write(f'  ... 共{len(bad)}\n')

out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_compare2_out.txt', 'w', encoding='utf-8')
compare(n, '【NEW 改进版 vs 金标准】', out)
out.close()
print('done')
