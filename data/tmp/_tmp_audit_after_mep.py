# -*- coding: utf-8 -*-
"""mep 分支治理后：全量 audit 统计（总体 + by_source）"""
import io
import sys

sys.path.insert(0, r'd:\projects\cost-estimation')

from src.pricing.judge_audit import run_judge_audit

OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_audit_after_mep_out.json'

s = run_judge_audit(export_path=None, limit=4000)
lines = [f"samples={s.get('samples')}  auto_fill_rate={s.get('auto_fill_rate')}"]
aa = s.get("accuracy_all", {})
for k, v in aa.items():
    lines.append(f"  {k}: {v}")
lines.append("--- by_source ---")
for src, d in sorted(s.get("by_source", {}).items(), key=lambda x: -x[1]["count"]):
    lines.append(f"  {src:32s} n={d['count']:5d}  core={d['core_ok_rate']:.3f}  strict={d['strict_ok_rate']:.3f}")
with io.open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\n".join(lines))
