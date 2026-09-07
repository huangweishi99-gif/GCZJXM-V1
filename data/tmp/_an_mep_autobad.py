# -*- coding: utf-8 -*-
"""临时：mep auto&core-fail 全集 + 特征分组。"""
import io, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

rows = json.loads(open(r"d:\projects\cost-estimation\data\tmp\_mep_rows.json", encoding="utf-8").read())

auto_bad = [x for x in rows if x["auto"] and not x["core_ok"]]
print(f"auto & core_FAIL: {len(auto_bad)} / auto总 {sum(1 for x in rows if x['auto'])}")

def brief(x):
    a_main, p_main = x["a_main"], x["p_main"]
    rel = "" if a_main <= 0 else f"{(p_main-a_main)/a_main*100:+.0f}%"
    return f"{x['record_id']:>6} {x['project_id']:<10}{x['name'][:24]:<24} 主{a_main:>8.1f}->{p_main:>8.1f}({rel:>5}) 人{x['a_labor']:>7.1f}->{x['p_labor']:>7.1f} | {x['feature'][:38]}"

for x in auto_bad:
    print("  " + brief(x))

print("\n=== auto & core_ok 采样(头10) ===")
for x in [y for y in rows if y["auto"] and y["core_ok"]][:10]:
    print("  " + brief(x))
