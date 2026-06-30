# -*- coding: utf-8 -*-
"""项目主材编号价 + 工艺份额 → 人材机分量。"""
from __future__ import annotations

from typing import Optional, Tuple

import re

from src.knowledge.project_materials import lookup_project_material_row, extract_material_codes
from src.pricing.custom_door import is_door_whole_line
from src.knowledge.query import PricingContext
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.cost_split import share_map
from src.normalize.craft_classifier import CraftMatch
from src.normalize.text import normalize_unit, normalize_name
from src.pricing.material_process_price import decompose_paint_material_price
from src.pricing.metal_trim import is_metal_trim_candidate, parse_unfold_mm
from src.pricing.tile_process_price import decompose_tile_material_price
from src.pricing.finish_material_process_price import (
    decompose_glass_material_price,
    decompose_stone_material_price,
    decompose_wood_veneer_material_price,
    decompose_vinyl_floor_material_price,
    decompose_wallpaper_material_price,
    decompose_wood_floor_material_price,
)

# 主材表价为「整板/整件」口径，清单按延长米+展开面计价的编号前缀
METER_TRIM_CODE_PREFIXES = ("MT", "AL")


def lookup_project_material_components(
    name: str,
    feature: str,
    unit: str,
    repo: KnowledgeRepository,
    craft: CraftMatch,
    *,
    ctx: Optional[PricingContext] = None,
    project_ref: Optional[str] = None,
) -> Tuple[Optional[dict], str]:
    """
    命中项目主材编号表时：主材=表价，人工/辅材/机械按工艺份额模板推算合价。
    """
    city = ctx.city if ctx else ""
    tier = ctx.price_tier if ctx else "mid"
    project_ref = (ctx.project_materials_ref if ctx else None) or project_ref
    text_norm = normalize_name(f"{name}\n{feature}")
    if is_door_whole_line(name, feature):
        return None, ""
    codes_early = extract_material_codes(name, feature)
    if len(codes_early) >= 2 and len({c.split("-")[0].upper() for c in codes_early}) >= 2:
        if re.search(r"定制|屏风", text_norm):
            return None, ""
    is_ct_kick = bool(re.search(r"踢脚", text_norm)) and bool(
        re.search(r"CT-\d+", text_norm, re.I)
    )

    row, note = lookup_project_material_row(
        name,
        feature,
        unit,
        city=city,
        price_tier=tier,
        project_ref=project_ref,
        db_path=repo.db_path,
    )
    # 踢脚延米清单：主材表为 ㎡ 价，回退用表价折算
    if not row and is_ct_kick and normalize_unit(unit) in ("m", "米"):
        row, note = lookup_project_material_row(
            name,
            feature,
            "㎡",
            city=city,
            price_tier=tier,
            project_ref=project_ref,
            db_path=repo.db_path,
        )
    if not row:
        return None, ""

    main_val = float(row["material_main"])
    if main_val <= 0:
        return None, ""

    code = str(row["material_code"])
    catalog_ok = bool(row.get("_from_project_catalog"))
    st_codes = list(dict.fromkeys(re.findall(r"ST-\d+(?:\.\d+)?", text_norm, re.I)))
    if len(st_codes) > 1 and code.upper().startswith("ST") and catalog_ok:
        prices: list[float] = []
        for sc in st_codes:
            r2, _ = lookup_project_material_row(
                sc,
                feature,
                unit,
                city=city,
                price_tier=tier,
                project_ref=project_ref,
                db_path=repo.db_path,
            )
            if r2:
                prices.append(float(r2.get("material_main") or 0))
        if prices and re.search(r"波打", text_norm):
            main_val = round(min(prices) * 1.66, 2)
        elif prices and re.search(r"拼花", text_norm):
            primary = extract_material_codes(name, "")[0] if extract_material_codes(name, "") else st_codes[0]
            for sc in st_codes:
                if sc.upper().startswith(primary.upper().split(".")[0]):
                    primary = sc
                    break
            r2, _ = lookup_project_material_row(
                primary, feature, unit, city=city, price_tier=tier,
                project_ref=project_ref, db_path=repo.db_path,
            )
            if r2:
                main_val = round(float(r2["material_main"]) * 1.66, 2)

    prefix = code.split("-")[0].upper()
    line_unit = normalize_unit(unit)
    row_unit = normalize_unit(str(row.get("unit_norm") or ""))

    if prefix in METER_TRIM_CODE_PREFIXES and line_unit in ("m", "米"):
        if is_metal_trim_candidate(name, feature, unit) or parse_unfold_mm(name, feature):
            return None, f"[项目主材表]{code}为板材㎡价，线条按展开面/m另计"

    # 含龙骨/板材基层的吊顶墙面：PT/AM 编号仅为饰面材料，不单套整项
    from src.pricing.material_process_price import analyze_paint_process

    if prefix == "MT" and re.search(r"玻镁板|方通|镀锌方通", text_norm):
        labor = 110.0 if "门套" in name else 85.0
        return {
            "material_main": main_val,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": labor,
            "machinery": 0.0,
        }, f"[工序拆价·{code}金属饰面+玻镁基层]主材=表价；人工{labor:.0f}；{note}"

    if prefix == "MR" and re.search(r"阻燃板|轻钢龙骨", text_norm):
        aux = 93.0 if re.search(r"不锈钢线条", text_norm) else 118.0
        return {
            "material_main": main_val,
            "material_loss_rate": 0.0,
            "material_aux": aux,
            "labor": 110.0,
            "machinery": 15.0,
        }, f"[工序拆价·{code}银镜+基层]主材=表价；人工110；{note}"

    scope = analyze_paint_process(name, feature)
    if scope.blocked_substrate and prefix in ("PT", "AM"):
        return None, f"[工序判断]含基层系统({code})，不单套饰面主材价"

    if row_unit and line_unit and row_unit != line_unit:
        area_units = {"m2", "㎡"}
        kick_units_ok = is_ct_kick and (
            (row_unit in area_units and line_unit in ("m", "米"))
            or (row_unit in area_units and line_unit in area_units)
        )
        if not kick_units_ok and not (row_unit in area_units and line_unit in area_units):
            return None, f"[单位不符]表价/{row_unit} vs 清单/{line_unit}"

    # 涂料类：按特征工序分解主材表价，不盲目整价套入
    paint_comps, paint_note = decompose_paint_material_price(
        code,
        str(row.get("material_name") or ""),
        main_val,
        name,
        feature,
        unit,
    )
    if paint_note.startswith("[工序判断]"):
        return None, paint_note
    if paint_comps:
        return paint_comps, f"{paint_note}；{note}"

    tile_comps, tile_note = decompose_tile_material_price(
        code,
        str(row.get("material_name") or ""),
        main_val,
        name,
        feature,
        unit,
    )
    if tile_comps:
        return tile_comps, f"{tile_note}；{note}"

    if prefix == "ST" and project_ref and not catalog_ok:
        return None, f"[项目主材表]{code}未录入本项目({project_ref})石材价库，请 import-project-materials 或 calibrate --learn 后补表"

    stone_comps, stone_note = decompose_stone_material_price(
        code,
        str(row.get("material_name") or ""),
        main_val,
        name,
        feature,
        unit,
        project_catalog=catalog_ok,
    )
    if stone_comps:
        return stone_comps, f"{stone_note}；{note}"

    for decompose in (
        decompose_glass_material_price,
        decompose_wood_veneer_material_price,
        decompose_wood_floor_material_price,
        decompose_vinyl_floor_material_price,
        decompose_wallpaper_material_price,
    ):
        comps, proc_note = decompose(
            code,
            str(row.get("material_name") or ""),
            main_val,
            name,
            feature,
            unit,
        )
        if comps:
            return comps, f"{proc_note}；{note}"

    if not text_norm or len(text_norm) < 8:
        return None, f"[项目主材表]{code}项目特征过短，无法按工序分解（须对照特征+单位）"

    if craft.craft_id == "generic_finish":
        return None, f"[项目主材表]{code}工艺未识别，禁止按份额盲套（须特征+单位）"

    shares = share_map(craft.template_share)
    main_share = shares.get("material_main") or 0.45
    if main_share < 0.05:
        main_share = 0.45

    total_est = main_val / main_share
    comps = {
        "material_main": main_val,
        "material_loss_rate": 0.0,
        "material_aux": round(total_est * shares.get("material_aux", 0.1), 2),
        "labor": round(total_est * shares.get("labor", 0.35), 2),
        "machinery": round(total_est * shares.get("machinery", 0.02), 2),
    }
    return comps, note
