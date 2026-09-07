# -*- coding: utf-8 -*-
"""按规则输出 当前表值 vs 失败行判/实中位数，自动建议新表值（传入真实city/tier）"""
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
OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_mr_fixplan_out.txt'

cfg = json.loads(Path(CFG).read_text(encoding='utf-8'))
rules = cfg['rules']

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
        feat_req = rule.get('feature_keywords') or []
        feat_hits = 0
        for kw in feat_req:
            kn = normalize_name(kw)
            if kn and kn in name_n:
                feat_hits += 1
                score += 8 + len(kn) * 0.05
        if feat_req and rule.get('require_feature_keywords') and feat_hits == 0:
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
    d = agg.setdefault(key, {'n': 0, 'em': [], 'el': [], 'pm': [], 'pl': [], 'names': [], 'cities': set()})
    d['n'] += 1
    d['em'].append(r['实_主材']); d['el'].append(r['实_人工'])
    d['pm'].append(r['判_主材']); d['pl'].append(r['判_人工'])
    d['cities'].add(str(r.get('城市', '')))
    if len(d['names']) < 2:
        d['names'].append(str(r['项目名称'])[:45])

buf = ['按规则对照（失败行，n>=4）:']
items = []
for key, d in agg.items():
    if d['n'] < 4:
        continue
    rule = next((r for r in rules if r['id'] == key), None)
    cur_m = rule.get('material_main', 0) if rule else None
    cur_l = rule.get('labor', 0) if rule else None
    cur_c = rule.get('confidence', 0.82) if rule else None
    em = statistics.median(d['em']); el = statistics.median(d['el'])
    pm = statistics.median(d['pm']); pl = statistics.median(d['pl'])
    sug_m = em if abs(pm - em) > 0.2 * max(em, 1e-9) else None
    sug_l = el if abs(pl - el) > 0.2 * max(el, 1e-9) else None
    match_ok = (pm == round(cur_m, 2) if cur_m is not None else True)
    items.append((key, d['n'], cur_m, pm, em, sug_m, cur_l, pl, el, sug_l, cur_c, d['names'], sorted(d['cities']), match_ok))

items.sort(key=lambda x: -x[1])
for key, n, cm, pm, em, sm, cl, pl, el, sl, cc, names, cities, mok in items:
    flag = '' if mok else '  ⚠判≠当前(需查歧义)'
    buf.append('\n[%s] x%d 置信=%.2f 城市=%s%s' % (key, n, cc if cc else 0, cities, flag))
    buf.append('  主材 当前=%s 判=%s 实=%s%s' % (
        '%.2f' % cm if cm is not None else '-',
        '%.2f' % pm, '%.2f' % em,
        '  >>改%.2f' % sm if sm is not None else ''))
    buf.append('  人工 当前=%s 判=%s 实=%s%s' % (
        '%.2f' % cl if cl is not None else '-',
        '%.2f' % pl, '%.2f' % el,
        '  >>改%.2f' % sl if sl is not None else ''))
    buf.append('  例: %s' % names)

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('done')
