# -*- coding: utf-8 -*-
"""临时：查看控制价对比分析结果，用后即删。"""
import io, sys, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import csv

rows = list(csv.DictReader(open(r"data\tmp\控制价对比分析.csv", encoding="utf-8-sig")))
print(f"总数={len(rows)}")

# 分类统计
stat = {"ctrl=0/空": 0, "cost=0": 0, "cost>ctrl": 0, "cost<ctrl": 0, "cost≈ctrl(±5%)": 0}
for r in rows:
    c = r["成本单价"]; k = r["控制价"]
    c = float(c) if c not in ("", None) else 0
    k = float(k) if k not in ("", None) else 0
    if k == 0:
        stat["ctrl=0/空"] += 1
    elif c == 0:
        stat["cost=0"] += 1
    else:
        d = float(r["差异%"]) if r["差异%"] not in ("", None) else 999
        if d > 5: stat["cost>ctrl"] += 1
        elif d < -5: stat["cost<ctrl"] += 1
        else: stat["cost≈ctrl(±5%)"] += 1
for k, v in stat.items():
    print(f"  {k}: {v}")

# 按差异排序
def key(r):
    d = r["差异%"]
    return float(d) if d not in ("", None) else 99999
rows_sorted = sorted(rows, key=key, reverse=True)

print("\n===== 差异最大（成本远高于控制价）前 25 =====")
for r in rows_sorted[:25]:
    print(f"  {r['文件'][:8]:10} {r['sheet'][:12]:12} 行{r['行']:>4} | {r['项目名称']:<24} | {r['单位']:>3} | 量{r['工程量']:>8} | 成本{r['成本单价']:>10} | 控制价{r['控制价']:>10} | 差异{r['差异%']:>8}%")

print("\n===== 差异最大（成本远低于控制价）前 20 =====")
for r in rows_sorted[-20:]:
    print(f"  {r['文件'][:8]:10} {r['sheet'][:12]:12} 行{r['行']:>4} | {r['项目名称']:<24} | {r['单位']:>3} | 量{r['工程量']:>8} | 成本{r['成本单价']:>10} | 控制价{r['控制价']:>10} | 差异{r['差异%']:>8}%")

# 无控制价的行（xls 中可能没有控制价）
print("\n===== 控制价为空的样本（前 15） =====")
n0 = [r for r in rows if r["控制价"] in ("", None) or float(r["控制价"] or 0) == 0]
print(f"  共 {len(n0)} 行")
for r in n0[:15]:
    print(f"  {r['文件'][:8]:10} {r['sheet'][:12]:12} 行{r['行']:>4} | {r['项目名称']:<24} | 成本{r['成本单价']}")
