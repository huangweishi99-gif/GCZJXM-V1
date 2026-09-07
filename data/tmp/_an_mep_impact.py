# -*- coding: utf-8 -*-
"""临时：评估候选修改的命中面。"""
import io, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

rows = json.loads(open(r"d:\projects\cost-estimation\data\tmp\_mep_rows.json", encoding="utf-8").read())

def is_elec(x):
    m = re.match(r"\[([^\]]+)\]", x["notes"] or "")
    return m and m.group(1) in ("电气",)

elec = [x for x in rows if is_elec(x)]
print(f"[电气] 桶 {len(elec)} 条")

print("\n-- 判主>=80 的高档命中（看高档档伤害面）--")
for x in elec:
    if x["p_main"] >= 80:
        print(f"  {x['record_id']:>6} p{x['project_id']:<3} 主{x['a_main']:>7.1f}->{x['p_main']:>7.1f} 人{x['a_labor']:>6.1f}->{x['p_labor']:>6.1f} {'OK' if x['core_ok'] else 'XX'} | {x['name'][:22]}")
print("\n-- 含16A/20A 的行 --")
for x in elec:
    if re.search(r"16A|20A|16安|20安", x["name"] + x["feature"]):
        print(f"  {x['record_id']:>6} p{x['project_id']:<3} 主{x['a_main']:>7.1f}->{x['p_main']:>7.1f} 人{x['a_labor']:>6.1f}->{x['p_labor']:>6.1f} {'OK' if x['core_ok'] else 'XX'} | {x['name'][:20]} | {x['feature'][:30].replace(chr(10),'/')}")
print("\n-- 含洁具词但被判[电气] 的行 --")
for x in elec:
    t = x["name"] + x["feature"]
    if re.search(r"小便器|大便器|洗手盆|洗面盆|台盆|马桶|蹲便|水槽|洗涤盆|拖把池|浴缸|淋浴|花洒|龙头|感应一体|落地便器", t):
        print(f"  {x['record_id']:>6} p{x['project_id']:<3} 主{x['a_main']:>7.1f}->{x['p_main']:>7.1f} {'OK' if x['core_ok'] else 'XX'} | {x['name'][:26]} | {x['feature'][:24].replace(chr(10),'/')}")
print("\n-- 含'盒'名称的[电气]行 --")
for x in elec:
    if re.search(r"(插座|开关|接线|底).{0,3}盒|盒$", x["name"]):
        print(f"  {x['record_id']:>6} p{x['project_id']:<3} 主{x['a_main']:>7.1f}->{x['p_main']:>7.1f} 人{x['a_labor']:>6.1f}->{x['p_labor']:>6.1f} {'OK' if x['core_ok'] else 'XX'} | {x['name'][:26]} | {x['feature'][:26].replace(chr(10),'/')}")
