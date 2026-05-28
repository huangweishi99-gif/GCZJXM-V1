"""无整项参照时，按材料品类+规格（如 600×600 地砖）查历史主材单价。"""
from __future__ import annotations

import statistics
from typing import List, Optional, Tuple

from rapidfuzz import fuzz

from src.normalize.material_spec import MaterialSpec, extract_material_spec
from src.normalize.paint_equiv import is_paint_item
from src.normalize.text import normalize_name, normalize_unit


def _size_in_text(size: str, text: str) -> bool:
    if not size or not text:
        return False
    w, h = size.split("*")
    variants = [
        f"{w}*{h}",
        f"{w}×{h}",
        f"{w}x{h}",
        f"{w}X{h}",
        f"{w}*{h}",
    ]
    t = normalize_name(text)
    return any(v in t for v in variants)


def _score_material_row(
    spec: MaterialSpec,
    name: str,
    feature: str,
    material_main: float,
) -> float:
    if material_main <= 0:
        return 0.0
    nn = normalize_name(name)
    ff = feature or ""
    text = nn + ff

    score = 0.0
    for kw in spec.keywords:
        if kw in nn or kw.lower() in text.lower():
            score += 0.35
            break

    if spec.size:
        if _size_in_text(spec.size, text):
            score += 0.45
        else:
            return 0.0
    else:
        score += 0.15

    if spec.thickness_mm and spec.thickness_mm in text:
        score += 0.1

    name_overlap = fuzz.token_set_ratio(normalize_name(spec.keywords[0] if spec.keywords else ""), nn) / 100.0
    score += 0.1 * name_overlap
    return min(score, 1.0)


class MaterialPriceLookup:
    def __init__(self, db_path: Optional[str] = None):
        from src.db.database import get_connection

        self._db_path = db_path
        self._get_conn = lambda: get_connection(db_path)

    def find(
        self,
        name: str,
        feature: str,
        unit: str,
        *,
        min_score: float = 0.55,
        top_n: int = 5,
        ctx=None,
    ) -> Tuple[Optional[dict], str]:
        spec = extract_material_spec(name, feature)
        if not spec:
            return None, "未识别材料品类/规格"

        un = normalize_unit(unit)
        mat_key = spec.category
        if spec.size:
            mat_key = f"{spec.category}:{spec.size}"

        if ctx is not None:
            from src.knowledge.query import query_material_price_fact

            conn = self._get_conn()
            try:
                fact, fnote = query_material_price_fact(conn, mat_key, un, ctx)
                if fact:
                    return {
                        "material_main": float(fact["material_main"]),
                        "material_loss_rate": float(fact.get("material_loss_rate") or 0),
                        "labor": 0.0,
                        "material_aux": 0.0,
                        "machinery": 0.0,
                        "_material_only": True,
                    }, f"[主材价库]{fnote}；规格{spec.size or spec.category}"
            finally:
                conn.close()

        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT cr.material_main, cr.material_loss_rate, cr.labor, cr.material_aux,
                          cr.machinery, si.name_norm, si.feature_norm, si.unit_norm
                   FROM cost_records cr
                   JOIN standard_items si ON si.id = cr.standard_item_id
                   WHERE cr.material_main IS NOT NULL AND cr.material_main > 0
                   ORDER BY cr.id DESC
                   LIMIT 8000"""
            ).fetchall()
        finally:
            conn.close()

        scored: List[Tuple[float, dict]] = []
        for r in rows:
            if un and normalize_unit(r["unit_norm"]) != un:
                continue
            s = _score_material_row(
                spec, r["name_norm"], r["feature_norm"] or "", float(r["material_main"])
            )
            if (
                spec.category == "paint"
                and is_paint_item(name, feature)
                and is_paint_item(r["name_norm"], r["feature_norm"] or "")
            ):
                s = max(s, 0.68)
            if s >= min_score:
                scored.append((s, dict(r)))

        if not scored:
            hint = f"{spec.category}"
            if spec.size:
                hint += f" {spec.size}"
            return None, f"库内无匹配主材价（{hint}）"

        scored.sort(key=lambda x: -x[0])
        top = scored[:top_n]
        mains = [float(t[1]["material_main"]) for t in top]
        med_main = float(statistics.median(mains))
        losses = [
            float(t[1]["material_loss_rate"])
            for t in top
            if t[1].get("material_loss_rate") is not None
        ]
        med_loss = float(statistics.median(losses)) if losses else 0.0

        best = top[0]
        note = (
            f"[主材参考]{best[1]['name_norm'][:24]} "
            f"规格匹配{best[0]:.0%}；主材中位数{med_main:.2f}（{len(top)}条样本）"
        )
        if spec.size:
            note += f"；规格{spec.size}"
        return {
            "material_main": med_main,
            "material_loss_rate": med_loss,
            "labor": 0.0,
            "material_aux": 0.0,
            "machinery": 0.0,
            "_material_only": True,
        }, note
