# -*- coding: utf-8 -*-
"""通宵心跳：跑 regression/audit，把失败簇写入日志供下一轮改进。"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LOG = ROOT / "data" / "exports" / "overnight_work_log.md"
STATE = ROOT / "data" / "exports" / "overnight_state.json"


def main() -> int:
    from src.db.database import get_connection
    from src.knowledge.query import PricingContext
    from src.knowledge.repository import KnowledgeRepository
    from src.normalize.craft_classifier import classify_craft
    from src.pricing.component_judge import judge_line_components
    from src.pricing.engine import PricingEngine
    from src.pricing.judge_audit import load_audit_samples, run_judge_audit

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    summary = run_judge_audit(limit=500, export_path=None)
    core = float(summary.get("accuracy_all", {}).get("core_main_and_labor") or 0)
    auto_core = float(
        summary.get("accuracy_auto_fill_only", {}).get("core_main_labor") or 0
    )
    auto_rate = float(summary.get("auto_fill_rate") or 0)

    repo = KnowledgeRepository()
    eng = PricingEngine()
    conn = get_connection()
    samples = load_audit_samples(conn, limit=500)
    fail_clusters: dict[str, list] = defaultdict(list)
    for s in samples:
        ctx = (
            PricingContext(city=s.city or "", price_tier=s.price_tier or "mid")
            if (s.city or s.price_tier)
            else None
        )
        j = judge_line_components(
            s.name,
            s.feature,
            s.unit,
            eng,
            repo,
            ctx=ctx,
            exclude_standard_item_id=s.standard_item_id,
        )
        craft = classify_craft(s.name, s.feature, s.unit)

        def ok(p: float, a: float) -> bool:
            if a <= 0.01:
                return p <= 5
            return abs(p - a) / a <= 0.2

        core_ok = ok(float(j.material_main or 0), s.actual["material_main"]) and ok(
            float(j.labor or 0), s.actual["labor"]
        )
        if not core_ok:
            key = f"{j.source}|{craft.craft_id}"
            fail_clusters[key].append(s.name[:40])

    top = sorted(fail_clusters.items(), key=lambda x: -len(x[1]))[:12]
    lines = [
        f"\n## Tick {now}",
        f"- core_all={core:.1%} auto_core={auto_core:.1%} auto_rate={auto_rate:.1%}",
        "- top fail clusters:",
    ]
    for k, names in top:
        c = Counter(names)
        sample = " / ".join(f"{n}×{v}" for n, v in c.most_common(3))
        lines.append(f"  - {len(names)} `{k}` :: {sample}")

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    state = {
        "time": now,
        "core_all": core,
        "auto_core": auto_core,
        "auto_rate": auto_rate,
        "top_fails": [{"cluster": k, "count": len(v)} for k, v in top],
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
