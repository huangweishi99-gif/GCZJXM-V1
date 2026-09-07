# -*- coding: utf-8 -*-
"""临时：按 mep note 标签分桶统计失败形态 + 改造零星词筛查。"""
import io, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from collections import defaultdict

rows = json.loads(open(r"d:\projects\cost-estimation\data\tmp\_mep_rows.json", encoding="utf-8").read())

def bucket(x):
    m = re.match(r"\[([^\]]+)\]", x["notes"] or "")
    if not m:
        return "无标签"
    tag = m.group(1)
    if "LED" in tag or "灯带" in tag:
        return "灯带/发光"
    if tag in ("风口/风阀/附件",):
        return "风口/风阀"
    return tag

agg = defaultdict(lambda: [0, 0, 0])  # n, core_ok, auto
for x in rows:
    b = bucket(x)
    agg[b][0] += 1
    agg[b][1] += 1 if x["core_ok"] else 0
    agg[b][2] += 1 if x["auto"] else 0

print("=== 按标签分桶（全部482）===")
for b, (n, ok, au) in sorted(agg.items(), key=lambda kv: -kv[1][0]):
    print(f"  {b:<14} n={n:>3}  core_ok={ok:>3} ({ok/n:.2f})  auto={au:>3} ({au/n:.2f})")

# 改造/零星词筛查（菜单2聚焦"位移/开孔"等电工零星项）
print("\n=== 含 移位/位移/开孔/凿(压)槽/拆除/恢复/调整/检修/新增 的名称 ===")
kws = ("移位", "位移", "开孔", "凿", "压槽", "拆除", "恢复", "调整", "检修", "新增", "迁移", "改造", "加装", "补", "剔")
hit = [x for x in rows if any(k in x["name"] for k in kws)]
for x in hit[:120]:
    okf = "ok" if x["core_ok"] else "XX"
    af = "A" if x["auto"] else " "
    rel = "" if x["a_main"] <= 0 else f"{(x['p_main']-x['a_main'])/x['a_main']*100:+.0f}%"
    print(f"  [{af}]{okf} {x['record_id']:>6} 主{x['a_main']:>8.1f}->{x['p_main']:>8.1f}({rel:>5}) 人{x['a_labor']:>7.1f}->{x['p_labor']:>7.1f} | {x['name'][:30]} | {x['notes'][:34]}")
print(f"\n改造词命中 {len(hit)}/{len(rows)}")

# 插座开关类（菜单焦点）细分
print("\n=== 名称含 插座/开关 全部 ===")
for x in [y for y in rows if "插座" in y["name"] or "开关" in y["name"]]:
    okf = "ok" if x["core_ok"] else "XX"
    af = "A" if x["auto"] else " "
    print(f"  [{af}]{okf} {x['record_id']:>6} {x['name'][:26]:<26} 主{x['a_main']:>8.1f}->{x['p_main']:>8.1f} 人{x['a_labor']:>7.1f}->{x['p_labor']:>7.1f} | {x['notes'][:30]}")
