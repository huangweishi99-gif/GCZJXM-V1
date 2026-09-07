# -*- coding: utf-8 -*-
"""按项目分片审计，输出 core 率，避免全量超时"""
import io
import sys

sys.path.insert(0, r'd:\projects\cost-estimation')

from src.pricing.judge_audit import run_judge_audit

PROJECTS = [
    (30, "深海大厦二期"),
    (31, "珠海海德会所"),
    (33, "珠海海德会所项目"),
    (47, "珠海海德会所精装修"),
    (37, "星河开市客2楼公区"),
    (40, "D座1207"),
    (41, "D座806-807"),
    (42, "D座3903-04-05-06"),
    (25, "龙华数字智造"),
    (34, "竹村更新单元"),
    (23, "中山医院"),
    (38, "B2户型"),
]

lines = []
tot_core = 0
tot_n = 0
for pid, pname in PROJECTS:
    try:
        s = run_judge_audit(export_path=None, project_id=pid)
        n = s.get("samples", 0)
        core = s.get("accuracy_all", {}).get("core_main_and_labor", 0)
        tot_core += core * n
        tot_n += n
        lines.append(f"  {pid:3d} {pname:16s} n={n:5d}  core={core:.3f}")
    except Exception as e:
        lines.append(f"  {pid:3d} {pname:16s} ERROR {e}")
if tot_n:
    lines.append(f"  --- 合计 n={tot_n} core={tot_core/tot_n:.3f}")

out = "\n".join(lines)
with io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_audit_by_project_out.txt', "w", encoding="utf-8") as f:
    f.write(out)
print(out)
