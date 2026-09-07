# -*- coding: utf-8 -*-
"""核实关键行的特征文本"""
import csv, io
rows = list(csv.DictReader(open(r"data\tmp\母行差异分析.csv", encoding="utf-8-sig")))
targets = {195, 852, 7, 39, 109, 130, 302, 38, 80, 83, 271, 274, 572}
for r in rows:
    if r["文件"] == "5#6#" and int(r["行"]) in targets or (r["文件"] == "会所xls" and int(r["行"]) in targets):
        print(f"=== {r['文件']} 行{r['行']} {r['项目名称'][:30]} | 单位={r['单位']} | 控制价={r['控制价']}")
        print("特征:", (r.get("特征", "") or "")[:300])
        print()
