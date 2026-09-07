# -*- coding: utf-8 -*-
"""全量 audit（limit=None）"""
import io
import sys

sys.path.insert(0, r'd:\projects\cost-estimation')

from src.pricing.judge_audit import run_judge_audit

s = run_judge_audit(export_path=None, limit=None)
lines = [f"samples={s.get('samples')}  auto_fill_rate={s.get('auto_fill_rate')}"]
aa = s.get("accuracy_all", {})
for k, v in aa.items():
    lines.append(f"  {k}: {v}")
lines.append("--- by_source ---")
for src, d in sorted(s.get("by_source", {}).items(), key=lambda x: -x[1]["count"]):
    lines.append(f"  {src:32s} n={d['count']:5d}  core={d['core_ok_rate']:.3f}  strict={d['strict_ok_rate']:.3f}")
out = "\n".join(lines)
with io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_audit_full_out.txt', "w", encoding="utf-8") as f:
    f.write(out)
print(out)
