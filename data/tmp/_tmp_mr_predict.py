# -*- coding: utf-8 -*-
"""精确预测：表值改为实值中位数后，各规则净收益（失败→成功 减 成功→失败）"""
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
OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_mr_predict_out.txt'

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

def rel_err(pred, actual):
    if actual <= 0.01:
        return 0.0 if pred <= 0.01 else 1.0
    return abs(pred - actual) / actual

def comp_ok(pred, actual):
    if actual <= 0.01:
        return pred <= 5.0
    return rel_err(pred, actual) <= 0.20

df = pd.read_excel(AUDIT, sheet_name='明细')
for c in ['核心OK']:
    df[c] = df[c].map(lambda v: str(v).strip().lower() in ('true', '1', 'yes', 'y'))
mr = df[df['判断来源'] == 'market_reference'].copy()

# 每个规则收集所有行（成功+失败）的实值
agg = {}
for _, r in mr.iterrows():
    rule = match_rule(r['项目名称'], r['单位'], r.get('城市', ''), r.get('档位', 'mid'))
    key = rule['id'] if rule else '!!未命中'
    d = agg.setdefault(key, {'rows': [], 'ok': 0})
    d['rows'].append(r)
    d['ok'] += int(bool(r['核心OK']))

buf = ['精确净收益预测（按净收益排序）:']
items = []
for key, d in agg.items():
    rows = d['rows']
    if len(rows) < 5:
        continue
    cur_ok = d['ok']
    # 修正建议 = 失败行实值中位数
    fail_rows = [r for r in rows if not r['核心OK']]
    em = statistics.median([r['实_主材'] for r in fail_rows]) if fail_rows else None
    el = statistics.median([r['实_人工'] for r in fail_rows]) if fail_rows else None
    # 模拟：全部行用新表值 em/el
    new_ok = 0
    for r in rows:
        pm = em if em is not None else r['判_主材']
        pl = el if el is not None else r['判_人工']
        if comp_ok(pm, r['实_主材']) and comp_ok(pl, r['实_人工']):
            new_ok += 1
    net = new_ok - cur_ok
    items.append((key, len(rows), cur_ok, new_ok, net, em, el, d['rows'][0]['项目名称']))

items.sort(key=lambda x: -x[4])
for key, tot, cur_ok, new_ok, net, em, el, name in items:
    buf.append('\n[%s] 总%d 当前OK%d -> 修正后OK%d | 净%d | 建议主材=%s 人工=%s' % (
        key, tot, cur_ok, new_ok, net,
        '%.2f' % em if em is not None else '-',
        '%.2f' % el if el is not None else '-'))
    buf.append('  例: %s' % name)

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('done')
