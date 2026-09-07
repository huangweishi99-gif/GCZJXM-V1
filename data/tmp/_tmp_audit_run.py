# -*- coding: utf-8 -*-
"""audit 统计（可传 limit 参数，如 python _tmp_audit_run.py 1500）"""
import io
import sys

sys.path.insert(0, r'd:\projects\cost-estimation')

limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

from src.pricing.judge_audit import run_judge_audit

s = run_judge_audit(export_path=None, limit=limit)
lines = [f"samples={s.get('samples')}  auto_fill_rate={s.get('auto_fill_rate')}"]
aa = s.get("accuracy_all", {})
for k, v in aa.items():
    lines.append(f"  {k}: {v}")
lines.append("--- by_source ---")
for src, d in sorted(s.get("by_source", {}).items(), key=lambda x: -x[1]["count"]):
    lines.append(f"  {src:32s} n={d['count']:5d}  core={d['core_ok_rate']:.3f}  strict={d['strict_ok_rate']:.3f}")
out = "\n".join(lines)
with io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_audit_run_out.txt', "w", encoding="utf-8") as f:
    f.write(out)
print(out)
