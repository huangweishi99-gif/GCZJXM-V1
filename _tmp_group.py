# -*- coding: utf-8 -*-
"""临时：差异>30%母行按(文件,名称,单位)分组（用后即删）。"""
import io, sys, os, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from collections import defaultdict

rows = list(csv.DictReader(open(r"data\tmp\母行差异分析.csv", encoding="utf-8-sig")))
bad = [r for r in rows if r["类型"] == "母行" and r["差异%"] not in (None, "")
       and abs(float(r["差异%"])) > 30]
print(f"差异>30% 母行总数: {len(bad)}")

groups = defaultdict(list)
for r in bad:
    key = (r["文件"], r["项目名称"], r["单位"])
    groups[key].append(r)

print(f"不同清单项(名称+单位): {len(groups)}")

import csv as _csv
with open(r"data\tmp\母行分组.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = _csv.writer(f)
    w.writerow(["文件", "项目名称", "单位", "行数", "行号", "控制价min", "控制价max", "现成本min", "现成本max", "最大差%", "特征样例", "工程量区间"])
    for g, rs in sorted(groups.items(), key=lambda x: -len(x[1])):
        f_, name, unit = g
        ctrls = sorted(float(r["控制价"]) for r in rs)
        costs = sorted(float(r["成本"]) for r in rs)
        diffmax = max(abs(float(r["差异%"])) for r in rs)
        rows_s = "、".join(str(r["行"]) for r in rs)
        w.writerow([f_, name, unit, len(rs), rows_s, ctrls[0], ctrls[-1], costs[0], costs[-1], f"{diffmax:.0f}%", "", ""])
print("CSV -> data/tmp/母行分组.csv")
# 同时打印控制台
for g, rs in sorted(groups.items(), key=lambda x: -len(x[1])):
    f, name, unit = g
    ctrls = sorted(float(r["控制价"]) for r in rs)
    costs = sorted(float(r["成本"]) for r in rs)
    print(f"[{f}] {name} | {unit} | {len(rs)}行 | 控制价{ctrls[0]}~{ctrls[-1]} | 现成本{costs[0]}~{costs[-1]}")
