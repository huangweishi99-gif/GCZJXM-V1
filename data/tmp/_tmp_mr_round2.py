# -*- coding: utf-8 -*-
"""第二轮分析：新audit明细中 market_reference 失败行 + 匹配歧义排查"""
import io
import json
import statistics
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, r'd:\projects\cost-estimation')
from src.normalize.text import normalize_name, normalize_unit

AUDIT = r'd:\projects\cost-estimation\data\exports\抽检报告_人材机判断.xlsx'
CFG = r'd:\projects\cost-estimation\config\market_reference_prices.json'
OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_mr_round2_out.txt'

cfg = json.loads(Path(CFG).read_text(encoding='utf-8'))
rules = cfg['rules']

# 1. 排查表值=0.46/7.10 或含 纸带/贴缝/网格 关键词的规则
buf = ['=== 匹配歧义排查：含 纸带/贴缝/网格/布 关键词的规则 ===']
for r in rules:
    kws = r.get('name_keywords', [])
    if any(any(k in kw for k in ('纸带', '贴缝', '网格', '胶带', '纱布', '防裂')) for kw in kws):
        buf.append('[%s] %s | 主材=%.2f 辅材=%.2f 人工=%.2f | excl=%s' % (
            r['id'], kws, r.get('material_main', 0), r.get('material_aux', 0),
            r.get('labor', 0), r.get('exclude_name_keywords', [])))

buf.append('\n=== 表值在 0.3-0.6 主材 或 6.5-7.5 人工 的规则（候选0.46/7.10来源）===')
for r in rules:
    mm = r.get('material_main', 0)
    lb = r.get('labor', 0)
    if 0.3 <= mm <= 0.7 or (6.0 <= lb <= 8.0 and mm < 2):
        buf.append('[%s] %s | 主材=%.2f 人工=%.2f' % (
            r['id'], r.get('name_keywords', [])[:3], mm, lb))

# 2. 重新聚合失败规则
def match_rule(name, unit, city, tier):
    name_n = normalize_name(name)
    unit_n = normalize_unit(unit)
    if not unit_n:
        return None
    city_n = normalize_name(city) if city else ''
    tier_n = (tier or 'mid').lower()
    demolition_context = any(k in name_n for k in ('拆除', '铲除', '剔凿', '刨铣'))
    best, best_score = None, 0.0
    for rule in rules:
        score = 0.0
        rule_id = str(rule.get('id', ''))
        if demolition_context and not (rule_id.startswith('demolition_') or rule.get('allow_demolition_context')):
            continue
        allowed = rule.get('units') or []
        if allowed and unit_n not in allowed:
            continue
        cities = [normalize_name(c) for c in (rule.get('cities') or []) if c]
        if cities and city_n and city_n not in cities:
            continue
        if cities and city_n and city_n in cities:
            score += 25.0
        tiers = [str(t).lower() for t in (rule.get('tiers') or []) if t]
        if tiers and tier_n not in tiers:
            continue
        if tiers and tier_n in tiers:
            score += 5.0
        name_hits = 0
        for kw in rule.get('name_keywords', []):
            kn = normalize_name(kw)
            if kn and kn in name_n:
                name_hits += 1
                score += 15 + len(kn) * 0.1
        if rule.get('name_keywords') and name_hits == 0:
            continue
        for kw in rule.get('exclude_name_keywords', []):
            kn = normalize_name(kw)
            if kn and kn in name_n:
                score = 0.0
                break
        if score <= 0:
            continue
        if score > best_score:
            best_score = score
            best = rule
    return best

df = pd.read_excel(AUDIT, sheet_name='明细')
for c in ['核心OK']:
    df[c] = df[c].map(lambda v: str(v).strip().lower() in ('true', '1', 'yes', 'y'))
mr = df[(df['判断来源'] == 'market_reference') & (~df['核心OK'])].copy()

agg = {}
for _, r in mr.iterrows():
    rule = match_rule(r['项目名称'], r['单位'], r.get('城市', ''), r.get('档位', 'mid'))
    key = rule['id'] if rule else '!!未命中'
    d = agg.setdefault(key, {'n': 0, 'em': [], 'el': [], 'pm': [], 'pl': [], 'names': [], 'feats': []})
    d['n'] += 1
    d['em'].append(r['实_主材']); d['el'].append(r['实_人工'])
    d['pm'].append(r['判_主材']); d['pl'].append(r['判_人工'])
    if len(d['names']) < 2:
        d['names'].append(str(r['项目名称'])[:45])
    if '项目特征' in df.columns and len(d['feats']) < 2:
        d['feats'].append(str(r.get('项目特征', ''))[:60])

buf.append('\n=== 第二轮失败规则（n>=4）===')
items = []
for key, d in agg.items():
    if d['n'] < 4:
        continue
    rule = next((r for r in rules if r['id'] == key), None)
    cur_m = rule.get('material_main', 0) if rule else None
    cur_l = rule.get('labor', 0) if rule else None
    em = statistics.median(d['em']); el = statistics.median(d['el'])
    pm = statistics.median(d['pm']); pl = statistics.median(d['pl'])
    items.append((key, d['n'], cur_m, pm, em, cur_l, pl, el, d['names'], d['feats']))

items.sort(key=lambda x: -x[1])
for key, n, cm, pm, em, cl, pl, el, names, feats in items:
    flag = '' if cm is not None and abs(pm - cm) < 0.01 else '  ⚠判≠当前'
    buf.append('\n[%s] x%d%s' % (key, n, flag))
    buf.append('  主材 当前=%s 判=%s 实=%s | 人工 当前=%s 判=%s 实=%s' % (
        '%.2f' % cm if cm is not None else '-', '%.2f' % pm, '%.2f' % em,
        '%.2f' % cl if cl is not None else '-', '%.2f' % pl, '%.2f' % el))
    buf.append('  例: %s' % names)
    if feats:
        buf.append('  特征: %s' % feats)

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('done')
