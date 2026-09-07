# -*- coding: utf-8 -*-
"""临时：mep auto 行的 conf 分布（评估阈值）。"""
import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from collections import Counter

rows = json.loads(open(r"d:\projects\cost-estimation\data\tmp\_mep_rows.json", encoding="utf-8").read())
auto = [x for x in rows if x["auto"]]
print("auto 总", len(auto))
c1 = Counter((x["conf"], x["core_ok"]) for x in auto)
for conf in sorted({x["conf"] for x in auto}):
    ok = c1[(conf, True)]; bad = c1[(conf, False)]
    print(f"  conf={conf:.2f}: ok={ok} bad={bad}  (auto-bad率 {bad/(ok+bad):.0%})")

# 若阈值提到 0.80：损失 auto-ok 数 vs 保留 auto-bad 数
for thr in (0.72, 0.76, 0.80, 0.84):
    kept_bad = sum(1 for x in auto if x["conf"] >= thr and not x["core_ok"])
    kept_ok = sum(1 for x in auto if x["conf"] >= thr and x["core_ok"])
    dropped_bad = sum(1 for x in auto if x["conf"] < thr and not x["core_ok"])
    dropped_ok = sum(1 for x in auto if x["conf"] < thr and x["core_ok"])
    print(f"阈值>{thr}: auto={kept_ok+kept_bad} (ok {kept_ok}/bad {kept_bad}), 砍掉 ok {dropped_ok} / bad {dropped_bad}")
