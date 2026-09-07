# -*- coding: utf-8 -*-
"""统计目标规则：总命中/成功/失败、实值分布、成功行实值"""
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
OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_mr_stats_out.txt'

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
mr = df[df['判断来源'] == 'market_reference'].copy()

agg = {}
for _, r in mr.iterrows():
    rule = match_rule(r['项目名称'], r['单位'], r.get('城市', ''), r.get('档位', 'mid'))
    key = rule['id'] if rule else '!!未命中'
    d = agg.setdefault(key, {'ok': [], 'fail': [], 'em': [], 'el': [], 'em_ok': [], 'el_ok': [], 'names': []})
    core_ok = bool(r['核心OK'])
    (d['ok'] if core_ok else d['fail']).append(r)
    d['em'].append(r['实_主材']); d['el'].append(r['实_人工'])
    if core_ok:
        d['em_ok'].append(r['实_主材']); d['el_ok'].append(r['实_人工'])
    if len(d['names']) < 2:
        d['names'].append(str(r['项目名称'])[:40])

buf = ['规则统计（按失败数排序）:']
items = []
for key, d in agg.items():
    if len(d['fail']) < 4:
        continue
    ok_n = len(d['ok']); fail_n = len(d['fail']); tot = ok_n + fail_n
    em = statistics.median(d['em']); el = statistics.median(d['el'])
    def pct(vals):
        return [round(statistics.quantiles(sorted(vals), n=4)[i], 2) for i in range(3)] if len(vals) >= 4 else '-'
    em_q = pct(d['em']); el_q = pct(d['el'])
    em_ok_q = pct(d['em_ok']) if d['em_ok'] else '-'
    items.append((key, tot, ok_n, fail_n, em, el, em_q, el_q, em_ok_q, d['names']))

items.sort(key=lambda x: -x[3])
for key, tot, ok_n, fail_n, em, el, em_q, el_q, em_ok_q, names in items:
    buf.append('\n[%s] 总%d=成功%d+失败%d' % (key, tot, ok_n, fail_n))
    buf.append('  实主材 中位=%.2f 四分位=%s | 实人工 中位=%.2f 四分位=%s' % (em, em_q, el, el_q))
    buf.append('  成功行实主材四分位=%s' % em_ok_q)
    buf.append('  例: %s' % names)

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('done')
