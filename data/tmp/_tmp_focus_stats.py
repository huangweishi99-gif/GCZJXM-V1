# -*- coding: utf-8 -*-
"""聚焦统计：只对目标来源/关键词样本跑 judge，验证改动无回归"""
import io
import sys

sys.path.insert(0, r'd:\projects\cost-estimation')
from src.db.database import get_connection
from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.pricing.component_judge import judge_line_components
from src.pricing.engine import PricingEngine
from src.pricing.judge_audit import _component_ok, load_audit_samples

TARGETS = sys.argv[1:] if len(sys.argv) > 1 else []

conn = get_connection()
try:
    samples = load_audit_samples(conn)
finally:
    conn.close()

repo = KnowledgeRepository()
engine = PricingEngine()

# 关键词组
KW_GROUPS = {
    "switch_socket": ("开关", "插座"),
    "door": ("门", "门套", "门框", "垭口"),
    "paint": ("涂料", "乳胶漆", "腻子", "面漆", "底漆", "肌理", "粉刷", "喷白"),
    "light": ("灯", "灯具", "筒灯", "射灯", "吸顶", "格栅", "光源"),
    "pipe": ("水管", "给水管", "排水管", "PPR", "PVC", "HDPE", "UPVC"),
}
SRC_FILTER = {
    "mep_install_profile": None,
    "custom_door_profile": None,
    "paint_process": None,
    "lighting_fixture_code": None,
    "plastic_pipe_dn": None,
}

if TARGETS:
    groups = {t: KW_GROUPS[t] for t in TARGETS if t in KW_GROUPS}
else:
    groups = {k: v for k, v in KW_GROUPS.items() if k in TARGETS or not TARGETS}

print(f"覆盖关键词组: {list(groups.keys())}")

from collections import Counter
src_counter = Counter()
ok_counter = Counter()
total_counter = Counter()

for s in samples:
    hit = any(
        any(k in (s.name or "") for k in kw) or any(k in (s.feature or "") for k in kw)
        for kw in groups.values()
    )
    if not hit:
        continue
    ctx = PricingContext(city=s.city, price_tier=s.price_tier)
    j = judge_line_components(
        s.name, s.feature, s.unit, engine, repo, ctx=ctx,
        exclude_standard_item_id=s.standard_item_id,
    )
    src_counter[j.source] += 1
    if j.source not in SRC_FILTER:
        continue
    total_counter[j.source] += 1
    pred = j.as_components()
    am = s.actual.get("material_main") or 0
    al = s.actual.get("labor") or 0
    main_ok = _component_ok(pred.get("material_main") or 0, am)
    labor_ok = _component_ok(pred.get("labor") or 0, al)
    core_ok = (main_ok if am > 0.01 else True) and (labor_ok if al > 0.01 else True)
    if core_ok:
        ok_counter[j.source] += 1

lines = []
for src in sorted(SRC_FILTER):
    n = total_counter[src]
    ok = ok_counter[src]
    if n:
        lines.append(f"  {src:28s} n={n:5d}  core={ok/max(1,n):.3f}  ({ok}/{n})")
lines.insert(0, "=== 目标来源 core_ok_rate ===")
lines.append("--- 全部命中样本来源分布 ---")
for src, n in src_counter.most_common():
    lines.append(f"  {src:32s} n={n}")
out = "\n".join(lines)
with io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_focus_stats_out.txt', "w", encoding="utf-8") as f:
    f.write(out)
print(out)
