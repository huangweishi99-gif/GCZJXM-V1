# -*- coding: utf-8 -*-
"""项目主材编号价表（如售楼处主材料.xlsx）导入与查询。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

import openpyxl

from src.db.database import get_connection
from src.knowledge.facts import upsert_material_fact_from_line
from src.normalize.text import normalize_name, normalize_unit

MATERIAL_CODE_RE = re.compile(
    r"([A-Z]{2}-\d{1,2}(?:\.\d{1,2})?[a-zA-Z]?)(?![A-Z0-9.\-])",
    re.I,
)

_CODE_CATEGORY = {
    "PT": "涂料",
    "GL": "玻璃",
    "MT": "金属",
    "AL": "金属",
    "CA": "地毯",
    "UP": "布艺皮革",
    "ST": "石材",
    "CT": "瓷砖",
    "CP": "毛毡",
    "WD": "木作",
    "SP": "其他饰面",
    "SF": "软装",
    "MR": "镜子",
    "DF": "其他饰面",
}


_SUPPLEMENTS_PATH = Path(__file__).resolve().parents[2] / "config" / "project_material_supplements.json"
_supplements_cache: Optional[dict] = None


def _load_supplements() -> dict:
    global _supplements_cache
    if _supplements_cache is not None:
        return _supplements_cache
    if not _SUPPLEMENTS_PATH.exists():
        _supplements_cache = {}
        return _supplements_cache
    _supplements_cache = json.loads(_SUPPLEMENTS_PATH.read_text(encoding="utf-8"))
    return _supplements_cache


def _supplement_material_row(
    code: str,
    *,
    project_ref: Optional[str],
    unit: str,
    city: str = "",
) -> Optional[dict]:
    refs = []
    if project_ref:
        refs.append(project_ref)
    if city:
        refs.append(f"city:{city}")
    for ref in refs:
        sup = _load_supplements().get(ref, {}).get(code.upper())
        if not sup:
            continue
        un = normalize_unit(str(sup.get("unit_norm") or "㎡"))
        line_u = normalize_unit(unit)
        if line_u and un and line_u != un and line_u not in ("m2", "㎡") and un in ("m2", "㎡"):
            pass
        elif line_u and un and line_u != un:
            continue
        return {
            "material_code": code.upper(),
            "material_name": str(sup.get("material_name") or code),
            "material_main": float(sup["material_main"]),
            "unit_norm": un,
            "project_name": ref,
            "project_ref": ref,
        }
    return None


def _material_try_codes(code: str) -> List[str]:
    """编号查价顺序：WD-03→WD-04；ST-01.02→ST-01。"""
    try_codes = [code.upper()]
    if code.upper() == "WD-03":
        try_codes.append("WD-04")
    m_sub = re.match(r"^(ST-\d+)\.\d+", code, re.I)
    if m_sub:
        parent = m_sub.group(1).upper()
        if parent not in try_codes:
            try_codes.append(parent)
    return try_codes


def extract_material_codes(name: str, feature: str = "") -> List[str]:
    """从名称+特征提取物料编号（PT-01、CT-01.02、ST-04a 等），去重保序（长编号优先）。"""
    text = f"{name or ''} {feature or ''}"
    seen: set[str] = set()
    raw: List[str] = []
    for m in MATERIAL_CODE_RE.finditer(text):
        code = m.group(1).upper()
        if code not in seen:
            seen.add(code)
            raw.append(code)
    raw.sort(key=lambda c: (-len(c), text.upper().find(c)))
    return raw


def _category_from_code(code: str) -> str:
    prefix = code.split("-")[0].upper()
    return _CODE_CATEGORY.get(prefix, "饰面")


_SECTION_WORDS = {"瓷砖类", "石材类", "木饰面", "涂料", "金属", "玻璃"}
_TAX_RATE_DEFAULT = 1.13


def _num(value) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _eval_arith(expr: str) -> Optional[float]:
    """仅四则运算，不执行任意代码。"""
    tokens = re.findall(r"\d+(?:\.\d+)?|[+\-*/()]", expr)
    if not tokens or "".join(tokens) != expr:
        return None
    pos = 0

    def peek() -> str:
        return tokens[pos] if pos < len(tokens) else ""

    def parse_expr() -> float:
        val = parse_term()
        while peek() in ("+", "-"):
            op = tokens[pos]
            nonlocal_advance()
            rhs = parse_term()
            val = val + rhs if op == "+" else val - rhs
        return val

    def nonlocal_advance() -> None:
        nonlocal pos
        pos += 1

    def parse_term() -> float:
        val = parse_factor()
        while peek() in ("*", "/"):
            op = tokens[pos]
            nonlocal_advance()
            rhs = parse_factor()
            if op == "/" and rhs == 0:
                raise ZeroDivisionError
            val = val * rhs if op == "*" else val / rhs
        return val

    def parse_factor() -> float:
        if peek() == "(":
            nonlocal_advance()
            val = parse_expr()
            if peek() != ")":
                raise ValueError
            nonlocal_advance()
            return val
        if peek() == "-":
            nonlocal_advance()
            return -parse_factor()
        tok = peek()
        if not tok or not tok[0].isdigit():
            raise ValueError
        nonlocal_advance()
        return float(tok)

    try:
        val = parse_expr()
    except (ValueError, ZeroDivisionError, IndexError):
        return None
    if pos != len(tokens):
        return None
    return val


def _eval_price_formula(formula: str, gross_by_row: dict, tax_rate: float) -> Optional[float]:
    """主材表含税价里的同行算术：=65+1.2*10、=(380+29)/1.2、=O34*1.6。"""
    expr = str(formula or "").strip()
    if not expr.startswith("="):
        return None
    expr = expr[1:].replace(" ", "")
    expr = re.sub(
        r"\$?O\$?(\d+)",
        lambda m: str(gross_by_row.get(int(m.group(1)), "")),
        expr,
    )
    expr = expr.replace("$", "")
    if not expr or not re.fullmatch(r"[0-9.+\-*/()]+", expr):
        return None
    val = _eval_arith(expr)
    if val is None or val != val or val <= 0:
        return None
    return val


def _net_from_gross(gross: float, tax_rate: float) -> float:
    rate = tax_rate if tax_rate and tax_rate > 1 else _TAX_RATE_DEFAULT
    return round(gross / rate, 2)


def import_project_materials_xlsx(
    file_path: str | Path,
    *,
    project_name: str,
    project_ref: str,
    city: str = "",
    price_tier: str = "mid",
    db_path: Optional[str] = None,
) -> dict:
    """
    导入项目主材表（物料编号、名称、单位、不含税主材价）。
    写入 project_material_prices，并同步 material_price_facts（key=code:PT-01）。
    """
    fp = Path(file_path)
    wb = openpyxl.load_workbook(fp, data_only=True)
    ws = wb.active
    rows_in: list = []
    section = ""

    for r in range(1, ws.max_row + 1):
        code = ws.cell(r, 1).value
        name = ws.cell(r, 2).value
        spec = ws.cell(r, 3).value
        area = ws.cell(r, 4).value
        unit = ws.cell(r, 6).value
        price = ws.cell(r, 7).value
        remark = ws.cell(r, 8).value

        if code and isinstance(code, str) and not re.match(r"^[A-Z]{2}-\d", code.strip(), re.I):
            if name and str(name).strip() and not price:
                section = str(name).strip()
            continue

        if not code or not isinstance(code, str):
            continue
        code = code.strip().upper()
        if not re.match(r"^[A-Z]{2}-\d", code):
            continue
        if price is None:
            continue
        try:
            price_f = float(price)
        except (TypeError, ValueError):
            continue
        if price_f <= 0:
            continue

        mat_name = str(name).strip() if name else code
        un = normalize_unit(str(unit) if unit else "㎡")
        rows_in.append(
            {
                "material_code": code,
                "material_name": mat_name,
                "name_norm": normalize_name(mat_name),
                "spec_text": str(spec).strip() if spec else "",
                "use_area": str(area).strip() if area else "",
                "unit_norm": un,
                "material_main": price_f,
                "category": section or _category_from_code(code),
                "remark": str(remark).strip() if remark else "",
            }
        )

    conn = get_connection(db_path)
    try:
        conn.execute(
            "DELETE FROM project_material_prices WHERE project_ref=? AND source_file=?",
            (project_ref, str(fp)),
        )
        for row in rows_in:
            conn.execute(
                """INSERT OR REPLACE INTO project_material_prices
                   (material_code, material_name, name_norm, spec_text, use_area,
                    unit_norm, material_main, category, project_name, project_ref,
                    city, price_tier, source_file, remark)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["material_code"],
                    row["material_name"],
                    row["name_norm"],
                    row["spec_text"],
                    row["use_area"],
                    row["unit_norm"],
                    row["material_main"],
                    row["category"],
                    project_name,
                    project_ref,
                    city or "",
                    price_tier or "mid",
                    str(fp),
                    row["remark"],
                ),
            )
            conn.execute(
                """INSERT INTO material_price_facts
                   (material_key, material_category, spec_text, unit_norm, city, price_tier,
                    material_main, material_loss_rate, sample_count)
                   VALUES (?,?,?,?,?,?,?,?,1)
                   ON CONFLICT(material_key, unit_norm, city, price_tier) DO UPDATE SET
                     material_main=excluded.material_main,
                     sample_count=sample_count+1,
                     updated_at=datetime('now','localtime')""",
                (
                    f"code:{row['material_code']}",
                    row["category"],
                    row["material_code"],
                    row["unit_norm"],
                    city or "",
                    price_tier or "mid",
                    row["material_main"],
                    0.0,
                ),
            )
            upsert_material_fact_from_line(
                conn,
                f"{row['material_code']} {row['material_name']}",
                row["spec_text"],
                row["unit_norm"],
                city or "",
                price_tier or "mid",
                row["material_main"],
                0.0,
            )
        conn.commit()
        total = conn.execute(
            "SELECT COUNT(*) c FROM project_material_prices WHERE project_ref=?",
            (project_ref,),
        ).fetchone()["c"]
    finally:
        conn.close()

    return {
        "imported": len(rows_in),
        "project_ref": project_ref,
        "project_name": project_name,
        "city": city,
        "price_tier": price_tier,
        "catalog_total": total,
        "source": str(fp),
        "codes": [r["material_code"] for r in rows_in],
    }


def import_named_materials_sheet(
    file_path: str | Path,
    *,
    project_name: str,
    project_ref: str,
    city: str = "",
    price_tier: str = "mid",
    sheet_name: str = "主材表",
    db_path: Optional[str] = None,
) -> dict:
    """导入无物料编号的项目主材表（重黔站房口径）。

    只写 project_material_prices，不进 material_price_facts。
    逐项价按品类取中位会把同城地砖、铝板价拉偏。
    含税价折不含税（默认 /1.13，取表头税率）；无含税价时用已填不含税价。
    """
    fp = Path(file_path)
    wb = openpyxl.load_workbook(fp, data_only=False)
    if sheet_name not in wb.sheetnames:
        wb.close()
        return {"imported": 0, "error": f"无工作表 {sheet_name}", "project_ref": project_ref}
    ws = wb[sheet_name]
    tax_rate = _num(ws.cell(2, 15).value) or _TAX_RATE_DEFAULT

    gross_by_row: dict = {}
    for r in range(4, ws.max_row + 1):
        gross = _num(ws.cell(r, 15).value)
        if gross and gross > 1:
            gross_by_row[r] = gross
    for r in range(4, ws.max_row + 1):
        if r in gross_by_row:
            continue
        raw = ws.cell(r, 15).value
        if isinstance(raw, str) and raw.startswith("="):
            val = _eval_price_formula(raw, gross_by_row, tax_rate)
            if val:
                gross_by_row[r] = val

    rows_in: list = []
    section = ""
    for r in range(4, ws.max_row + 1):
        name = ws.cell(r, 3).value
        name_s = str(name).strip() if name else ""
        if name_s in _SECTION_WORDS or (name_s and not ws.cell(r, 1).value and not ws.cell(r, 6).value):
            section = name_s
            continue
        if not name_s:
            continue
        unit = ws.cell(r, 6).value
        un = normalize_unit(str(unit) if unit else "")
        if not un:
            continue
        gross = gross_by_row.get(r)
        net = _num(ws.cell(r, 12).value)
        if gross and gross > 1:
            price_f = _net_from_gross(gross, tax_rate)
            price_note = f"含税{gross:g}/税率{tax_rate:g}"
        elif net and net > 1:
            price_f = round(net, 2)
            price_note = "表内不含税价"
        else:
            continue
        loss = _num(ws.cell(r, 13).value) or 0.0
        spec = ws.cell(r, 9).value
        area = ws.cell(r, 8).value
        code_cell = ws.cell(r, 2).value
        code = str(code_cell).strip().upper() if code_cell else f"NAME-{r}"
        rows_in.append(
            {
                "material_code": code,
                "material_name": name_s[:80],
                "name_norm": normalize_name(name_s),
                "spec_text": str(spec).strip() if spec else "",
                "use_area": str(area).strip() if area else "",
                "unit_norm": un,
                "material_main": price_f,
                "loss_rate": loss,
                "category": section or "饰面",
                "remark": f"主材表逐项价·{price_note}·损耗{loss:g}",
            }
        )
    wb.close()

    conn = get_connection(db_path)
    try:
        conn.execute(
            "DELETE FROM project_material_prices WHERE project_ref=? AND source_file=?",
            (project_ref, str(fp)),
        )
        for row in rows_in:
            conn.execute(
                """INSERT OR REPLACE INTO project_material_prices
                   (material_code, material_name, name_norm, spec_text, use_area,
                    unit_norm, material_main, category, project_name, project_ref,
                    city, price_tier, source_file, remark)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["material_code"],
                    row["material_name"],
                    row["name_norm"],
                    row["spec_text"],
                    row["use_area"],
                    row["unit_norm"],
                    row["material_main"],
                    row["category"],
                    project_name,
                    project_ref,
                    city or "",
                    price_tier or "mid",
                    str(fp),
                    row["remark"],
                ),
            )
        conn.commit()
        total = conn.execute(
            "SELECT COUNT(*) c FROM project_material_prices WHERE project_ref=?",
            (project_ref,),
        ).fetchone()["c"]
    finally:
        conn.close()

    return {
        "imported": len(rows_in),
        "project_ref": project_ref,
        "project_name": project_name,
        "city": city,
        "price_tier": price_tier,
        "tax_rate": tax_rate,
        "catalog_total": total,
        "source": str(fp),
        "synced_material_facts": False,
        "names": [r["material_name"] for r in rows_in],
    }


def collect_st_prices_from_gold(
    gold_path: str | Path,
    *,
    project_ref: str,
    project_name: str,
    city: str = "",
    price_tier: str = "mid",
    db_path: Optional[str] = None,
    code_prefixes: tuple[str, ...] = ("ST",),
) -> dict:
    """
    从金标准清单采集项目编号→主材表价（同编号取中位数）。
    拼花/波打/错位等行会还原为物料书表价（÷1.66），避免与工序拆价重复乘系数。
    不覆盖已用物料书 xlsx 导入的行。
    """
    from src.knowledge.calibration import load_priced_map

    gold_map = load_priced_map(gold_path)
    by_code: dict[str, list[dict]] = {}
    for row in gold_map.values():
        text = normalize_name(f"{row.name}\n{row.feature or ''}")
        codes = extract_material_codes(row.name, row.feature or "")
        for code in codes:
            prefix = code.split("-")[0].upper()
            if prefix not in code_prefixes:
                continue
            main = float(row.material_main or 0)
            if main <= 0:
                continue
            if prefix == "PT":
                continue
            if prefix == "MT" and main < 300:
                continue
            if prefix == "ST":
                if re.search(r"拼花|波打|错位", text):
                    main = round(main / 1.66, 2)
                elif re.search(r"20mm", text) and re.search(r"地面|楼地面", text):
                    if not re.search(r"拼花|波打", text) and main > 550:
                        main = round(main / 1.22, 2)
                if re.search(r"玻镁|方通|湿贴", text) and main > 600:
                    main = 450.0
            by_code.setdefault(code, []).append(
                {
                    "material_main": main,
                    "material_name": (row.name or code).split("\n")[0][:80],
                    "unit_norm": normalize_unit(row.unit or "㎡"),
                    "is_plain": not re.search(r"拼花|波打|错位", text),
                }
            )

    conn = get_connection(db_path)
    inserted = updated = skipped = 0
    try:
        for code, samples in sorted(by_code.items()):
            plain = [s for s in samples if s.get("is_plain")]
            pool = plain if plain else samples
            mains = sorted(s["material_main"] for s in pool)
            mid = mains[len(mains) // 2]
            if code.upper().startswith("ST-") and mid > 600:
                mid = 450.0
            mat_name = pool[0]["material_name"]
            un = samples[0]["unit_norm"] or "㎡"
            existing = conn.execute(
                """SELECT id, source_file, remark FROM project_material_prices
                   WHERE material_code=? AND project_ref=? AND unit_norm=?""",
                (code, project_ref, un),
            ).fetchone()
            if existing and existing["source_file"] and "金标准采集" not in (
                existing["remark"] or ""
            ):
                skipped += 1
                continue
            conn.execute(
                """INSERT INTO project_material_prices
                   (material_code, material_name, name_norm, spec_text, use_area,
                    unit_norm, material_main, category, project_name, project_ref,
                    city, price_tier, source_file, remark)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(material_code, project_ref, unit_norm) DO UPDATE SET
                     material_main=excluded.material_main,
                     material_name=excluded.material_name,
                     name_norm=excluded.name_norm,
                     remark=excluded.remark""",
                (
                    code,
                    mat_name,
                    normalize_name(mat_name),
                    "",
                    "",
                    un,
                    mid,
                    "石材",
                    project_name,
                    project_ref,
                    city or "",
                    price_tier or "mid",
                    str(gold_path),
                    f"金标准采集·{len(samples)}项·中位{mid:.2f}",
                ),
            )
            if existing:
                updated += 1
            else:
                inserted += 1
            conn.execute(
                """INSERT INTO material_price_facts
                   (material_key, material_category, spec_text, unit_norm, city, price_tier,
                    material_main, material_loss_rate, sample_count)
                   VALUES (?,?,?,?,?,?,?,?,1)
                   ON CONFLICT(material_key, unit_norm, city, price_tier) DO UPDATE SET
                     material_main=excluded.material_main,
                     sample_count=sample_count+1,
                     updated_at=datetime('now','localtime')""",
                (
                    f"code:{code}",
                    "石材",
                    mat_name,
                    un,
                    city or "",
                    price_tier or "mid",
                    mid,
                    0.0,
                ),
            )
            upsert_material_fact_from_line(
                conn,
                f"{code} {mat_name}",
                "",
                un,
                city or "",
                price_tier or "mid",
                mid,
                0.0,
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "project_ref": project_ref,
        "codes_seen": len(by_code),
        "inserted": inserted,
        "updated": updated,
        "skipped_xlsx": skipped,
    }


def _is_project_catalog_row(row: dict, project_ref: Optional[str]) -> bool:
    """表价是否来自当前项目价库（非跨项目/城市混用）。"""
    if not project_ref:
        return False
    ref = str(row.get("project_ref") or "")
    return ref == project_ref or ref == f"city:{project_ref}"


def lookup_project_material_row(
    name: str,
    feature: str,
    unit: str,
    *,
    city: str = "",
    price_tier: str = "mid",
    project_ref: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Tuple[Optional[dict], str]:
    """
    按清单名称/特征中的物料编号查项目主材价。
    返回 (row_dict, note) 或 (None, "")。
    """
    codes = extract_material_codes(name, feature)
    if not codes:
        return None, ""

    un = normalize_unit(unit)
    conn = get_connection(db_path)
    try:
        for code in codes:
            for tc in _material_try_codes(code):
                row = None
                from_supplement = False
                if project_ref:
                    row = conn.execute(
                        """SELECT * FROM project_material_prices
                           WHERE material_code=? AND project_ref=?
                             AND (unit_norm=? OR unit_norm='' OR ?='')""",
                        (tc, project_ref, un, un),
                    ).fetchone()
                    if not row:
                        row = _supplement_material_row(
                            tc, project_ref=project_ref, unit=unit, city=city
                        )
                        from_supplement = row is not None
                else:
                    for city_try in ([city, ""] if city else [""]):
                        for tier_try in ([price_tier, "mid"] if price_tier else ["mid"]):
                            row = conn.execute(
                                """SELECT * FROM project_material_prices
                                   WHERE material_code=? AND city=? AND price_tier=?
                                     AND (unit_norm=? OR unit_norm='' OR ?='')
                                   ORDER BY project_ref DESC LIMIT 1""",
                                (tc, city_try, tier_try, un, un),
                            ).fetchone()
                            if row:
                                break
                        if row:
                            break
                    if not row:
                        row = _supplement_material_row(
                            tc, project_ref=None, unit=unit, city=city
                        )
                        from_supplement = row is not None
                if not row:
                    continue
                row_dict = dict(row) if not isinstance(row, dict) else row
                row_dict["_from_project_catalog"] = _is_project_catalog_row(
                    row_dict, project_ref
                )
                stone_name = str(row_dict.get("material_name") or tc)
                prefix = "[补充表价]" if from_supplement else "[项目主材表]"
                note = (
                    f"{prefix}{row_dict.get('project_name', project_ref or '')}·{tc}·"
                    f"{stone_name} 主材{float(row_dict['material_main']):.2f}/"
                    f"{row_dict.get('unit_norm', '')}"
                )
                if tc != code.upper():
                    note = f"{note}（{code}→{tc}）"
                if not row_dict.get("_from_project_catalog") and project_ref:
                    note = f"{note}；⚠非本项目价库，ST/编号表价不跨项目套用"
                return row_dict, note
    finally:
        conn.close()
    return None, ""


def lookup_project_material_by_name(
    name: str,
    feature: str,
    unit: str,
    *,
    project_ref: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Tuple[Optional[dict], str]:
    """无物料编号时，按清单名称匹配本项目主材表（不跨项目）。

    全等优先；否则清单名以主材名为前缀（防水面砖墙面 → 防水面砖）。
    不拿特征里的「地砖/铝板」去套整表，避免把做法描述当成主材行。
    多个前缀同时命中时取最长名，避免「地砖」套到「地砖地面」。
    """
    if not project_ref:
        return None, ""
    key = normalize_name(name)
    if not key or len(key) < 2:
        return None, ""
    un = normalize_unit(unit)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM project_material_prices
               WHERE project_ref=?
                 AND (unit_norm=? OR unit_norm='' OR ?='')""",
            (project_ref, un, un),
        ).fetchall()
    finally:
        conn.close()
    exact = [r for r in rows if r["name_norm"] == key]
    if exact:
        chosen = exact
        how = "名称"
    else:
        # 只认清单里真实出现的部位后缀，禁止「地砖地面」套「地砖梯面」
        _suffixes = ("墙面", "地面", "楼面", "踢脚", "吊顶", "顶棚")
        prefixed = [
            r for r in rows
            if r["name_norm"] and len(r["name_norm"]) >= 4 and key.startswith(r["name_norm"])
            and key[len(r["name_norm"]):] in _suffixes
        ]
        if not prefixed:
            return None, ""
        best_len = max(len(r["name_norm"]) for r in prefixed)
        chosen = [r for r in prefixed if len(r["name_norm"]) == best_len]
        how = "名称后缀"
    row_dict = dict(chosen[0])
    row_dict["_from_project_catalog"] = True
    note = (
        f"[项目主材表·{how}]{row_dict.get('project_name') or project_ref}·"
        f"{row_dict.get('material_name')} 主材{float(row_dict['material_main']):.2f}/"
        f"{row_dict.get('unit_norm') or ''}"
    )
    if len(chosen) > 1:
        note = f"{note}（同长{len(chosen)}条，取首条）"
    return row_dict, note
