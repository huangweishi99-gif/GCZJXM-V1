"""招标清单组价：精确/模糊匹配 + 成本填入。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.match.engine import (
    MatchMode,
    MatchThresholds,
    best_match,
    classify_level,
    rank_candidates,
    should_auto_fill,
)
from src.pricing.calc import calc_from_components


class PricingEngine:
    def __init__(self, db_path: Optional[str] = None, match_mode: Optional[str] = None):
        self.repo = KnowledgeRepository(db_path)
        self.settings = self.repo.settings
        self.match_cfg = self.settings.get("match", {})
        self.price_cfg = self.settings.get("pricing", {})
        mode_str = match_mode or self.match_cfg.get("mode", "auto")
        self.mode = MatchMode(mode_str)
        self.thresholds = MatchThresholds.from_config(self.match_cfg)

    def _load_pool(self, conn) -> List[dict]:
        rows = conn.execute(
            """SELECT id, name_norm, feature_norm, unit_norm, method_signature,
                      feature_tags_json, method_summary, sample_count
               FROM standard_items WHERE sample_count > 0"""
        ).fetchall()
        return [dict(r) for r in rows]

    def run_for_project(self, tender_project_id: int) -> Dict[str, Any]:
        conn = self.repo.conn()
        try:
            lines = conn.execute(
                """SELECT * FROM boq_lines WHERE project_id=? ORDER BY id""",
                (tender_project_id,),
            ).fetchall()
            pool = self._load_pool(conn)
            cur = conn.execute(
                """INSERT INTO pricing_jobs (project_id, status) VALUES (?, 'draft')""",
                (tender_project_id,),
            )
            job_id = int(cur.lastrowid)
            ctx: PricingContext = self.repo.get_project_context(tender_project_id)

            filled = 0
            exact_count = 0
            fuzzy_count = 0
            unmatched = 0

            for line in lines:
                candidate, level = best_match(
                    line["name"],
                    line["feature"] or "",
                    line["unit"],
                    pool,
                    th=self.thresholds,
                    mode=self.mode,
                )
                conf = candidate.total_score if candidate else 0.0
                sid = candidate.standard_item_id if candidate else None
                agg: Dict[str, float] = {}
                note = "未匹配到历史成本，请人工组价"

                if candidate:
                    mlabel = "精确" if candidate.match_type == "exact" else "模糊"
                    if level == "A":
                        exact_count += 1
                    elif level == "B":
                        fuzzy_count += 1
                    records = (
                        self.repo.get_cost_records_for_item(sid, ctx=ctx) if sid else []
                    )
                    method_note = f"做法「{candidate.method_summary}」"
                    if candidate.tag_conflicts:
                        method_note += "；" + "；".join(candidate.tag_conflicts)
                    if records and should_auto_fill(level, self.mode, candidate.tag_conflicts):
                        agg = self.repo.aggregate_costs(records)
                        note = (
                            f"[{mlabel}{level}级]「{candidate.name_norm}」"
                            f"名称{candidate.name_score:.0%} 特征文{candidate.feature_score:.0%} "
                            f"做法{candidate.tag_score:.0%}；{method_note}；{len(records)}条历史"
                        )
                        filled += 1
                    elif records:
                        agg = self.repo.aggregate_costs(records)
                        note = (
                            f"[{mlabel}参考]「{candidate.name_norm}」{conf:.0%}，"
                            f"等级{level}需人工确认；{method_note}"
                        )
                    else:
                        note = f"命中标准项但无成本记录（{mlabel}）"
                        level = "C"
                else:
                    unmatched += 1

                qty = float(line["quantity"] or 0)
                mgmt_r = self.price_cfg.get("default_management_rate", 0)
                prof_r = self.price_cfg.get("default_profit_rate", 0)
                tax_r = self.price_cfg.get("default_tax_rate", 0)

                conflicts = candidate.tag_conflicts if candidate else []
                use_agg = bool(agg) and should_auto_fill(level, self.mode, conflicts)
                bd = calc_from_components(
                    material_main=float(agg.get("material_main") or 0) if use_agg else 0,
                    material_loss_rate=float(agg.get("material_loss_rate") or 0) if use_agg else 0,
                    labor=float(agg.get("labor") or 0) if use_agg else 0,
                    material_aux=float(agg.get("material_aux") or 0) if use_agg else 0,
                    machinery=float(agg.get("machinery") or 0) if use_agg else 0,
                    management_rate=mgmt_r,
                    profit_rate=prof_r,
                    tax_rate=tax_r,
                )
                if not use_agg:
                    bd = calc_from_components(0, 0, 0, 0, 0)

                cost_amt, amount = bd.with_quantity(qty) if qty and use_agg else (None, None)

                conn.execute(
                    """INSERT INTO pricing_lines
                       (job_id, boq_line_id, match_level, confidence, standard_item_id,
                        source_record_count, material_main, material_loss_rate, material_aux,
                        labor, machinery, management, profit, tax,
                        cost_unit_price, cost_amount, unit_price, amount, match_note)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        job_id,
                        line["id"],
                        level,
                        conf,
                        sid,
                        len(self.repo.get_cost_records_for_item(sid)) if sid else 0,
                        bd.material_main if use_agg else None,
                        bd.material_loss_rate if use_agg else None,
                        bd.material_aux if use_agg else None,
                        bd.labor if use_agg else None,
                        bd.machinery if use_agg else None,
                        bd.management if use_agg else None,
                        bd.profit if use_agg else None,
                        bd.tax if use_agg else None,
                        bd.cost_unit_price if use_agg else None,
                        cost_amt,
                        bd.unit_price if use_agg else None,
                        amount,
                        note,
                    ),
                )

            conn.commit()
            return {
                "job_id": job_id,
                "tender_project_id": tender_project_id,
                "match_mode": self.mode.value,
                "total_lines": len(lines),
                "auto_filled": filled,
                "exact_matched": exact_count,
                "fuzzy_matched": fuzzy_count,
                "need_review": len(lines) - filled,
                "unmatched": unmatched,
            }
        finally:
            conn.close()

    def search(
        self,
        name: str,
        feature: str,
        unit: str,
        top_n: int = 5,
        exclude_standard_item_ids: Optional[set] = None,
    ) -> List[dict]:
        conn = self.repo.conn()
        try:
            pool = self._load_pool(conn)
            if exclude_standard_item_ids:
                pool = [p for p in pool if p["id"] not in exclude_standard_item_ids]
        finally:
            conn.close()
        cands = rank_candidates(
            name, feature, unit, pool, top_n=top_n, th=self.thresholds, mode=self.mode
        )
        out = []
        for c in cands:
            level = classify_level(
                c.name_score,
                c.feature_score,
                c.tag_score,
                c.total_score,
                self.thresholds,
                self.mode,
                c.tag_conflicts,
            )
            out.append(
                {
                    "standard_item_id": c.standard_item_id,
                    "name": c.name_norm,
                    "feature": c.feature_norm[:80],
                    "unit": c.unit_norm,
                    "做法摘要": c.method_summary,
                    "name_score": round(c.name_score, 4),
                    "feature_score": round(c.feature_score, 4),
                    "tag_score": round(c.tag_score, 4),
                    "total_score": round(c.total_score, 4),
                    "match_type": c.match_type,
                    "level": level,
                    "conflicts": "; ".join(c.tag_conflicts) if c.tag_conflicts else "",
                    "samples": c.sample_count,
                }
            )
        return out
