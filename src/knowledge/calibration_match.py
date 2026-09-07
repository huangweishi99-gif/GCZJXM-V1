# -*- coding: utf-8 -*-
"""校准对比用匹配键：在保留导出 dedupe 的前提下，放宽招标/定稿分项命名差。"""
from __future__ import annotations

import re

from src.link.dedupe import make_dedupe_key
from src.normalize.text import normalize_name, normalize_unit
from src.pricing.decorative_diffuser import _parse_length_width_mm

_MAT_CODE_RE = re.compile(
    r"^(CL|ST|CT|WD|WP|PT|MT|AM|SI)-(\d{2})(?![0-9])",
    re.I,
)

# 定稿 vs 招标分项名称别名（仅校准匹配）
_MAT_NAME_ALIASES: tuple[tuple[str, str], ...] = (
    (r"背栓式干挂门槛石", "石材门槛"),
    (r"干挂及背栓", ""),
)


def _normalize_project_name(name: str, project_id: str) -> str:
    nn = normalize_name(name)
    if project_id == "shenhai_dasha":
        nn_si = re.sub(r"^SI-02", "ST-02", nn, flags=re.I)
        if nn_si != nn:
            nn = nn_si
    return nn


def _normalize_mat_line_name(name: str, project_id: str) -> str:
    """弱化招标/定稿间修饰差（平光面、燃烧等级等），保留 4m/9m/凹凸等实质后缀。"""
    nn = _normalize_project_name(name, project_id)
    nn = re.sub(r"\(平光面\)", "", nn)
    nn = re.sub(r"[（(]燃烧性能等级A级[）)]", "", nn)
    nn = re.sub(r"\(燃烧性能等级A级\)", "", nn)
    for pat, rep in _MAT_NAME_ALIASES:
        nn = re.sub(pat, rep, nn)
    return normalize_name(nn)


def _material_calibration_key(name: str, unit: str, project_id: str) -> str | None:
    nn = _normalize_mat_line_name(name, project_id)
    m = _MAT_CODE_RE.match(nn)
    if not m:
        return None
    fam = m.group(1).upper()
    if project_id == "shenhai_dasha" and fam == "SI":
        fam = "ST"
    return f"mat|{fam}-{m.group(2)}|{nn}|{normalize_unit(unit)}"


def _vent_product_key(feature: str, name: str = "") -> tuple[str, str]:
    text = feature or ""
    m_name = re.search(r"名称[:：]([^\n2]+)", text)
    vent = normalize_name(m_name.group(1)) if m_name else ""
    if not vent:
        mw = re.search(r"(\d{2,3})宽", text) or re.search(r"(\d{2,3})宽", name)
        if mw:
            vent = f"{mw.group(1)}宽风口"
        elif "风口" in name:
            vent = normalize_name(name)
    length_mm, width_mm = _parse_length_width_mm(text)
    spec = f"{length_mm}*{width_mm}".lower() if length_mm and width_mm else ""
    return vent, spec


def _vent_band_key(feature: str, unit: str, name: str = "") -> str | None:
    """风口按「产品+宽度」聚合（忽略长度拆分差），单价按延长米比。"""
    vent, spec = _vent_product_key(feature, name)
    if not spec or "*" not in spec:
        return None
    width_mm = spec.split("*", 1)[1]
    product = vent or "装饰风口"
    return f"vent_band|{product}|w{width_mm}|{normalize_unit(unit)}"


def _electrical_panel_key(name: str, feature: str, unit: str) -> str | None:
    if "低压电气" not in normalize_name(name):
        return None
    text = feature or ""
    m = re.search(r"名称[:：]([^\n]+)", text)
    if not m:
        return None
    panel = normalize_name(m.group(1).split("【", 1)[0].strip())
    return f"elec_panel|{panel}|{normalize_unit(unit)}"


def _lighting_strip_key(name: str, feature: str, unit: str) -> str | None:
    """装饰灯/灯带按特征「名称」产品型号区分（避免同名弱套）。"""
    un = normalize_unit(unit)
    if un not in ("m", "米"):
        return None
    nn = normalize_name(name)
    text = feature or ""
    if "装饰灯" not in nn and "灯带" not in nn and "灯带" not in text:
        return None
    m = re.search(r"名称[:：]\s*([^\n]+)", text)
    prod = normalize_name(m.group(1)) if m else ""
    if not prod and "灯带" not in text and "线性" not in text:
        return None
    return f"light_strip|{prod or nn}|{un}"


def make_calibration_match_key(
    name: str,
    feature: str,
    unit: str,
    *,
    project_id: str = "",
) -> str:
    """
    校准专用匹配键（≠ 导出 dedupe）：
    - 深海 SI-02 → ST-02；主材编号按规范化名称+单位
    - 装饰风口按「产品+宽度」延长米带聚合（shenhai）
    - 低压电气开关按特征「名称」配电箱编号
    """
    nn = _normalize_project_name(name, project_id)
    un = normalize_unit(unit)

    if project_id == "shenhai_dasha":
        elec = _electrical_panel_key(name, feature, unit)
        if elec:
            return elec

        light = _lighting_strip_key(name, feature, unit)
        if light:
            return light

        if nn == "前台":
            return f"furniture|前台|{un}"

        mat_key = _material_calibration_key(name, unit, project_id)
        if mat_key:
            return mat_key

        if "装饰风口" in nn:
            band = _vent_band_key(feature, unit, name)
            if band:
                return band

    if "装饰风口" in nn:
        vent, spec = _vent_product_key(feature, name)
        return f"装饰风口|{vent}|{spec}|{un}"

    nn0, un, sig = make_dedupe_key(name, feature, unit)
    nn_dedupe = _normalize_project_name(nn0, project_id)
    return f"{nn_dedupe}|{sig}|{un}"


def vent_band_rate_from_row(feature: str, quantity: float, cost_unit: float) -> tuple[float, float]:
    """返回 (延长米工程量, 元/延长米)。"""
    length_mm, _ = _parse_length_width_mm(feature or "")
    if not length_mm or quantity <= 0 or cost_unit <= 0:
        return 0.0, 0.0
    meters = length_mm / 1000.0 * float(quantity)
    if meters <= 0:
        return 0.0, 0.0
    return meters, float(cost_unit) * float(quantity) / meters
