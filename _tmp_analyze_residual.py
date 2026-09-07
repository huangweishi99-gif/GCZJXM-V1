# -*- coding: utf-8 -*-
import io, sys, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
rows = list(csv.DictReader(open(r"data\tmp\母行测算结果.csv", encoding="utf-8-sig")))
bad = [r for r in rows if r["新差异%"] not in (None, "") and abs(float(r["新差异%"])) > 30]
print(f"总计 {len(rows)} 条, >30% 残余 {len(bad)} 条\n")
for r in sorted(bad, key=lambda x: -abs(float(x["新差异%"]))):
    print(f"[{r['文件'][:8]}] 行{r['行']:>4} | {r['项目名称'][:40]:<40} | {r['单位']:<4} | "
          f"控制价{r['控制价']:>8} 现成本{r['现成本']:>7} 现差异{r['现差异%']:>6}% -> "
          f"新成本{r['新成本']:>7} 新差异{r['新差异%']:>6}% | {r['分析'][:36]}")
