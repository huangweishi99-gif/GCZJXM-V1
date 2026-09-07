# -*- coding: utf-8 -*-
"""用文件原文 name/feature 跑 judge，对比金标准，统计 source 分布"""
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
import openpyxl
from src.knowledge.repository import KnowledgeRepository
from src.pricing.engine import PricingEngine
from src.knowledge.query import PricingContext
from src.pricing.component_judge import judge_line_components

GOLD = r'd:\projects\cost-estimation\清单数据资料\AI学习清单\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价-20260818.xlsx'
repo = KnowledgeRepository()
engine = PricingEngine()
ctx = PricingContext(city='江门', price_tier='mid')

wb = openpyxl.load_workbook(GOLD, data_only=True, read_only=True)
ws = wb['标准层户型85']
rows = [list(r) for r in ws.iter_rows(values_only=True)]
wb.close()

def v(x):
    if x is None or x == '':
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None

out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_real_judge_out.txt', 'w', encoding='utf-8')
src_count = {}
n = 0
ok_main = ok_labor = ok_both = 0
bad = []
sect = ''
for i, r in enumerate(rows):
    name = str(r[2] or '').strip()
    if not name:
        continue
    if r[1] and str(r[1]).startswith('一'):
        sect = name
        continue
    g_main = v(r[10])  # K 主材单价e
    g_labor = v(r[8])  # I 人工费b
    if g_labor is None:
        continue
    n += 1
    feat = str(r[3] or '')
    unit = str(r[6] or '')
    j = judge_line_components(name, feat, unit, engine, repo, ctx=ctx)
    src_count[j.source] = src_count.get(j.source, 0) + 1
    m_main = float(j.material_main or 0)
    m_labor = float(j.labor or 0)
    def rel(a, b):
        if b == 0:
            return 0.0 if a == 0 else None
        return abs(a - b) / b
    r_main = rel(m_main, g_main) if g_main is not None else None
    r_labor = rel(m_labor, g_labor)
    ok_m = r_main is not None and r_main <= 0.20
    ok_l = r_labor is not None and r_labor <= 0.20
    if ok_m:
        ok_main += 1
    if ok_l:
        ok_labor += 1
    if ok_m and ok_l:
        ok_both += 1
    else:
        bad.append((i, sect, name, g_main, m_main, g_labor, m_labor, j.source))

out.write(f'总行 {n}  主材OK {ok_main} ({ok_main/max(n,1):.0%})  人工OK {ok_labor} ({ok_labor/max(n,1):.0%})  主材+人工OK {ok_both} ({ok_both/max(n,1):.0%})\n')
out.write(f'source分布: {src_count}\n\n')
out.write('== 未通过行 ==\n')
for i, s, nm, g_m, m_m, g_l, m_l, src in bad[:80]:
    out.write(f'L{i+1} [{s}] {nm[:20]} | 主材 实{g_m} 判{m_m} | 人工 实{g_l} 判{m_l} | {src}\n')
out.close()
print(f'done n={n} ok_both={ok_both} src={src_count}')
