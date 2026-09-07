# -*- coding: utf-8 -*-
"""临时：聚焦查看开关插座/开孔/底盒 样本 feature。"""
import io, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from collections import Counter

rows = json.loads(open(r"d:\projects\cost-estimation\data\tmp\_mep_rows.json", encoding="utf-8").read())

ab = [x for x in rows if x["auto"] and not x["core_ok"]]
print("auto-bad by project:", dict(Counter(x["project_id"] for x in ab)))
print("auto-bad by note桶:", dict(Counter(re.match(r"\[([^\]]+)\]", x["notes"]).group(1) for x in ab if re.match(r"\[([^\]]+)\]", x["notes"]))))

def show(x, wide=True):
    rel = "" if x["a_main"] <= 0 else f"{(x['p_main']-x['a_main'])/x['a_main']*100:+.0f}%"
    print(f"\n[{x['record_id']}] {x['name'][:46]} | 主{x['a_main']:>8.1f}->{x['p_main']:>8.1f}({rel}) 人{x['a_labor']:>7.1f}->{x['p_labor']:>7.1f}")
    print(f"  unit={x['unit']} note={x['notes'][:60]}")
    print(f"  feat: {x['feature'][:150]}")

# 1) 开关插座混乱系列（名 = 开关插座）
print("\n===== A. 名称=开关插座 (151xx 系列) =====")
for x in rows:
    if str(x["record_id"]).startswith(("1515", "1516", "1517")):
        show(x)

# 2) 底盒/开孔
print("\n===== B. 开关（插座）盒 / 开孔 =====")
for x in rows:
    if "盒" in x["name"] or "开孔" in x["name"] or "凿" in x["name"]:
        show(x)
