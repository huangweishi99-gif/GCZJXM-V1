# -*- coding: utf-8 -*-
"""列出 母行测算结果.csv 中新差异>30% 的行，筛查规则误配"""
import csv, io

rows = list(csv.DictReader(open("data/tmp/母行测算结果.csv", encoding="utf-8-sig")))
out = io.open("data/tmp/_big_rows.txt", "w", encoding="utf-8")
out.write("total: %d\n" % len(rows))

big = [r for r in rows if abs(float(r.get("新差异%", 0))) > 30]
out.write("新差异 >30%%: %d\n" % len(big))
for r in big:
    out.write("|".join([
        r.get("文件", ""), "行" + str(r.get("行", "")),
        (r.get("项目名称", "") or "")[:34], "单位=" + r.get("单位", ""),
        "量=" + r.get("工程量", ""), "控=" + r.get("控制价", ""),
        "现=" + r.get("现成本", ""), "现差%=" + r.get("现差异%", ""),
        "新主=" + r.get("新主材", ""), "新工=" + r.get("新人工", ""),
        "新辅=" + r.get("新辅材", ""), "新机=" + r.get("新机械", ""),
        "新成=" + r.get("新成本", ""), "新差%=" + r.get("新差异%", ""),
        "分析=" + (r.get("分析", "") or "")[:44],
    ]) + "\n")
out.close()
print("done", len(big))
