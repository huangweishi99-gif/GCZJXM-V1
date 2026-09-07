# -*- coding: utf-8 -*-
"""塑料管按 DN 规格拆价（开市客/深海金标准口径）。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from src.normalize.text import normalize_name, normalize_unit

# ========== 口径 B：纯管材价（招标特征不含"含管道配件"时，珠海会所等口径） ==========
# (主材, 人工, 辅材+机械) 元/m - 基于实际样本校准
# 注意：这个表用于塑料管（PPR等）
_PIPE_DN_TABLE = {
    # 实际样本：PPR给水管De110(DN100) 主材36.0, 人工30.0, 辅材+机械2.5
    "DN100": (36.0, 30.0, 2.5),
    # 实际样本：PPR给水管De90(DN80) 主材28.0, 人工28.0, 辅材+机械2.0
    "DN80": (28.0, 28.0, 2.0),
    # 实际样本：PPR给水管De75(DN65) 主材22.0, 人工25.0, 辅材+机械1.8
    "DN65": (22.0, 25.0, 1.8),
    # 实际样本：PPR给水管De63(DN50) 主材15.0, 人工24.0, 辅材+机械1.5
    # 实际样本：PPR热给水管De63(DN50) 主材47.10, 人工23.68, 辅材0.42+机械0.05
    "DN50": (47.10, 23.68, 0.47),
    # 实际样本：PPR给水管De50(DN40) 主材20.12, 人工23.68, 辅材+机械0.38
    "DN40": (20.12, 23.68, 0.38),
    # 实际样本：PPR给水管De40(DN32) 主材11.59, 人工23.68, 辅材+机械0.32
    "DN32": (11.59, 23.68, 0.32),
    # 实际样本：PPR给水管De32(DN25) 主材8.5, 人工22.09, 辅材+机械0.3
    "DN25": (8.5, 22.09, 0.3),
    # 实际样本：PPR给水管De25(DN20) 主材4.5, 人工18.0, 辅材+机械0.3
    "DN20": (4.5, 18.0, 0.3),
    # 实际样本：PPR给水管De20(DN15) 主材3.2, 人工20.0, 辅材+机械0.9（海德项目校准）
    "DN15": (3.2, 20.0, 0.9),
}

# ========== 口径 A：主材含管道配件（招标特征含"含管道配件"时，深圳开市客等口径） ==========
# (主材, 辅材, 人工, 机械) 元/m - 辅材≈主材×0.5、人工≈口径B×0.45，总量与口径B一致
# 实际样本：深圳 PPR给水管 DN15/20/25/50/65（特征明确"含管道配件"）
_PIPE_FITTING_DN_TABLE = {
    "DN15": (9.64, 4.82, 9.16, 0.48),
    "DN20": (9.89, 4.94, 9.40, 0.49),
    "DN25": (10.59, 5.29, 10.06, 0.53),
    # 插值：介于 DN25(10.59) 与 DN50(16.56)
    "DN32": (12.5, 6.25, 12.0, 0.6),
    "DN40": (14.5, 7.25, 13.5, 0.7),
    # 实际样本：深圳 PPR给水管 DN50 主16.56/人15.73
    "DN50": (16.56, 8.28, 15.73, 0.83),
    # 实际样本：深圳 PPR给水管 DN65 主23.50/人22.33
    "DN65": (23.50, 11.75, 22.33, 1.18),
    # 插值（HDPE DN75 参考）
    "DN80": (27.0, 13.5, 25.5, 1.35),
    "DN100": (37.0, 18.5, 35.0, 1.8),
}

# ========== HDPE 排水管（深圳口径，柔性承插） ==========
# (主材, 辅材, 人工, 机械) 元/m
_HDPE_DN_TABLE = {
    # 实际样本：HDPE单层管DN50 主12.48/辅6.24/人11.86/机0.62
    "DN50": (12.48, 6.24, 11.86, 0.62),
    # 实际样本：HDPE单层管DN75 主25.80/辅12.90/人24.51/机1.29
    "DN75": (25.80, 12.90, 24.51, 1.29),
    # 实际样本：HDPE单层管DN100 主37.12/辅18.56/人35.26/机1.86
    "DN100": (37.12, 18.56, 35.26, 1.86),
}

# ========== 静音排水管（深圳口径，比普通HDPE贵约30%） ==========
# (主材, 辅材, 人工, 机械) 元/m
_SILENT_DN_TABLE = {
    # 实际样本：高密度HDPE静音排水管DN50 主17.28/辅8.64/人16.42/机0.86
    "DN50": (17.28, 8.64, 16.42, 0.86),
    # 实际样本：高密度HDPE静音排水管DN75 主33.80/辅16.90/人32.11/机1.69
    "DN75": (33.80, 16.90, 32.11, 1.69),
}

# ========== UPVC 冷凝水管（含接头管件+保温，人工低） ==========
# (主材, 辅材, 人工, 机械) 元/m
_UPVC_CONDENSATE_DN_TABLE = {
    # 实际样本：UPVC冷凝水管DN25 主6.10/人5.80（粘接连接，含弯头三通+13mm保温）
    "DN25": (6.10, 1.0, 5.80, 0.1),
    # 实际样本：UPVC冷凝水管DN32 主7.04/人6.68
    "DN32": (7.04, 1.0, 6.68, 0.1),
    # 实际样本：云湾安装定稿 UPVC冷凝水管DN40 主14.0/辅1.0/人18.0/机0.1
    "DN40": (14.0, 1.0, 18.0, 0.1),
}

# ========== UPVC 排水管（粘接连接，人工高于 PPR 给水管） ==========
# (主材, 人工, 辅材+机械) 元/m - 会所合并清单-20260705 与云湾安装定稿双源一致
_UPVC_DRAIN_DN_TABLE = {
    # 会所合并清单-20260705 + 云湾安装定稿：UPVC排水管DN100 主36.0/辅1.53/人55.0/机0.27
    "DN100": (36.0, 55.0, 1.8),
    # 会所安装清单：UPVC排水管DN75 主18.0/辅1.27/人45.0/机0.23
    "DN75": (18.0, 45.0, 1.5),
    # 会所安装清单：UPVC排水管DN50 主10.0/辅1.02/人20.0/机0.18
    "DN50": (10.0, 20.0, 1.2),
}

# 铸铁排水管价格（实际样本校准）- (主材, 人工, 辅材, 机械) 元/m
# 注意：这个表只用于铸铁排水管，DN值范围与塑料管不同
_CAST_IRON_DN_TABLE = {
    # 实际样本：铸铁排水管DN200 主材123.62, 人工77.35, 辅材4.33, 机械33.87
    "DN200": (123.62, 77.35, 4.33, 33.87),
    # 实际样本：铸铁排水管DN150 主材92.1, 人工72.96, 辅材3.85, 机械24.13
    "DN150": (92.1, 72.96, 3.85, 24.13),
    # 实际样本：铸铁排水管DN100 主材62.1, 人工68.8, 辅材3.76, 机械15.59
    "DN100": (62.1, 68.8, 3.76, 15.59),
    # 实际样本：铸铁排水管DN75 主材38.0, 人工45.0, 辅材2.5, 机械8.0
    "DN75": (38.0, 45.0, 2.5, 8.0),
    # 实际样本：铸铁排水管DN65 主材56.2, 人工49.08, 辅材2.78, 机械2.63
    "DN65": (56.2, 49.08, 2.78, 2.63),
    # 实际样本：铸铁排水管DN50 主材52.5, 人工39.55, 辅材1.63, 机械1.31
    "DN50": (52.5, 39.55, 1.63, 1.31),
    # 实际样本：铸铁排水管DN40（参考值）
    "DN40": (35.0, 32.0, 1.5, 1.5),
}

# 球磨铸铁管价格（实际样本校准）- 用于给水，价格更高 - (主材, 人工, 辅材, 机械) 元/m
# 注意：这个表只用于球墨铸铁管
_DUCTILE_IRON_DN_TABLE = {
    # 实际样本：球磨铸铁管DN150 主材132.1, 人工54.87, 辅材2.64, 机械24.41
    "DN150": (132.1, 54.87, 2.64, 24.41),
    # 实际样本：球磨铸铁管DN100 主材107.5, 人工45.82, 辅材1.84, 机械18.12
    "DN100": (107.5, 45.82, 1.84, 18.12),
    # 实际样本：球磨铸铁管DN80 主材115.26, 人工29.83, 辅材1.26, 机械2.91
    "DN80": (115.26, 29.83, 1.26, 2.91),
    # 实际样本：球磨铸铁管DN65 主材94.05, 人工29.83, 辅材1.26, 机械2.91
    "DN65": (94.05, 29.83, 1.26, 2.91),
    # 实际样本：球磨铸铁管DN50 主材76.53, 人工29.83, 辅材1.26, 机械2.91
    "DN50": (76.53, 29.83, 1.26, 2.91),
    # 实际样本：球磨铸铁管DN40 主材55.01, 人工29.83, 辅材1.26, 机械2.91
    "DN40": (55.01, 29.83, 1.26, 2.91),
}

# 所有管道类型的DN表
_ALL_DN_TABLES = {
    "plastic": _PIPE_DN_TABLE,
    "plastic_fitting": _PIPE_FITTING_DN_TABLE,
    "hdpe": _HDPE_DN_TABLE,
    "silent": _SILENT_DN_TABLE,
    "upvc_condensate": _UPVC_CONDENSATE_DN_TABLE,
    "cast_iron": _CAST_IRON_DN_TABLE,
    "ductile_iron": _DUCTILE_IRON_DN_TABLE,
}

# 衬塑钢管/钢塑复合管的识别关键词
_NON_PLASTIC_PIPE_KEYWORDS = ["衬塑", "钢塑", "复合管", "镀锌钢管", "焊接钢管", "无缝钢管"]

_SPEC_STOP = re.compile(r"改|旧管|替换|备注|修缮")

# De（塑料管公称直径）到 DN 的映射
_DE_TO_DN = {
    20: "DN15", 25: "DN20", 32: "DN25", 40: "DN32",
    50: "DN40", 63: "DN50", 75: "DN65", 90: "DN80",
    110: "DN100",
}


def _dn_from_digits_for_table(digits: str, table: dict) -> Optional[str]:
    """从DN数字字符串中提取有效的DN值，仅在指定表中查找。
    
    优先匹配完整的DN值，只有在完整匹配失败时才尝试截断版本。
    """
    # 首先尝试完整匹配
    dn_full = f"DN{int(digits)}"
    if dn_full in table:
        return dn_full
    
    # 如果完整匹配失败，再尝试截断版本
    if len(digits) > 2:
        trials = [digits[:2], digits[:3], digits[:-1]]
        for d in trials:
            if not d:
                continue
            dn = f"DN{int(d)}"
            if dn in table:
                return dn
    return None


def _dn_from_digits(digits: str) -> Optional[str]:
    """从DN数字字符串中提取有效的DN值，在所有表中查找。"""
    all_dns = set()
    for table in _ALL_DN_TABLES.values():
        all_dns.update(table.keys())
    
    trials = [digits]
    if len(digits) > 2:
        trials.extend([digits[:2], digits[:3], digits[:-1]])
    seen: set[str] = set()
    for d in trials:
        if not d or d in seen:
            continue
        seen.add(d)
        dn = f"DN{int(d)}"
        if dn in all_dns:
            return dn
    return None


def _first_dn_in_text(text: str, table: Optional[dict] = None) -> Optional[str]:
    """从文本中提取第一个DN值，可选地限定在指定表中查找。"""
    # 先找 DN 前缀
    for m in re.finditer(r"DN\s*(\d+)", text, re.I):
        if table:
            dn = _dn_from_digits_for_table(m.group(1), table)
        else:
            dn = _dn_from_digits(m.group(1))
        if dn:
            return dn
    # 再找 De 前缀（塑料管公称直径）
    for m in re.finditer(r"De\s*(\d+)", text, re.I):
        de = int(m.group(1))
        if de in _DE_TO_DN:
            dn = _DE_TO_DN[de]
            if dn and (table is None or dn in table):
                return dn
    return None


def _spec_feature_block(feature: str) -> str:
    """规格描述段：遇「改旧管/修缮」等备注行即截断，避免误取他径。"""
    lines: list[str] = []
    for line in normalize_name(feature or "").split("\n"):
        if _SPEC_STOP.search(line):
            break
        lines.append(line)
    return "\n".join(lines[:8])


def _extract_dn_for_table(name: str, feature: str, table: dict) -> Optional[str]:
    """从名称和特征中提取DN值，仅在指定表中查找。"""
    # 名称中的DN优先
    dn = _first_dn_in_text(normalize_name(name), table)
    if dn:
        return dn
    # 特征中的DN
    spec = _spec_feature_block(feature)
    if spec:
        dn = _first_dn_in_text(spec, table)
        if dn:
            return dn
    # 完整特征中的DN
    return _first_dn_in_text(normalize_name(feature or ""), table)


def _extract_dn(name: str, feature: str) -> Optional[str]:
    """从名称和特征中提取DN值（在所有表中查找）。"""
    # 名称中的DN优先
    dn = _first_dn_in_text(normalize_name(name))
    if dn:
        return dn
    # 特征中的DN
    spec = _spec_feature_block(feature)
    if spec:
        dn = _first_dn_in_text(spec)
        if dn:
            return dn
    # 完整特征中的DN
    return _first_dn_in_text(normalize_name(feature or ""))


def _is_non_plastic_pipe(text: str) -> bool:
    """检查是否为非塑料管（衬塑钢管、钢塑复合管等）。"""
    return any(kw in text for kw in _NON_PLASTIC_PIPE_KEYWORDS)


def lookup_plastic_pipe_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """名称/特征含塑料管+DN 或铸铁管+DN时按管径表价拆人材机。"""
    if normalize_unit(unit) not in ("m", "米"):
        return None, ""
    text = normalize_name(f"{name}\n{feature}")
    
    # 第一步：排除非塑料管（衬塑钢管、钢塑复合管等）
    # 这些管道的价格体系不同，不应使用塑料管定价
    if _is_non_plastic_pipe(text):
        return None, ""
    
    # 第二步：检测球墨铸铁管（用于给水，价格更高）
    # 必须同时包含"球磨"和"铸铁"
    if "球磨" in text and "铸铁" in text:
        dn = _extract_dn_for_table(name, feature, _DUCTILE_IRON_DN_TABLE)
        if dn:
            main, labor, aux, mach = _DUCTILE_IRON_DN_TABLE[dn]
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[球墨铸铁管·{dn}]主材{main:.1f}+人工{labor:.0f}"
        # DN提取失败则返回None，不回退到其他管道类型
        return None, ""
    
    # 第三步：检测铸铁排水管（价格体系独立）
    # 必须包含"铸铁"关键词，且不能是球墨铸铁管（已在上面处理）
    if "铸铁" in text:
        dn = _extract_dn_for_table(name, feature, _CAST_IRON_DN_TABLE)
        if dn:
            main, labor, aux, mach = _CAST_IRON_DN_TABLE[dn]
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[铸铁排水管·{dn}]主材{main:.1f}+人工{labor:.0f}"
        # DN提取失败则返回None，不回退到塑料管
        return None, ""
    
    # 第四步：检测塑料管（PPR等）
    # 必须包含塑料管相关关键词
    if not any(k in text for k in ("塑料管", "给水管", "排水管", "PPR", "ppr", "冷凝水管")):
        return None, ""
    
    # ---- 子类优先：静音排水管 > HDPE > UPVC冷凝水管 > PPR/给排水管 ----
    # 静音排水管（高密度HDPE静音，比普通HDPE贵约30%）
    if re.search(r"静音|螺旋消音|螺旋降噪", text):
        dn = _extract_dn_for_table(name, feature, _SILENT_DN_TABLE)
        if dn:
            main, aux, labor, mach = _SILENT_DN_TABLE[dn]
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[静音排水管·{dn}]主材{main:.1f}+人工{labor:.0f}"
        return None, ""
    
    # HDPE 单层管/双壁波纹（柔性承插或热熔承插）
    if re.search(r"HDPE|单层管|双壁波纹", text):
        dn = _extract_dn_for_table(name, feature, _HDPE_DN_TABLE)
        if dn:
            main, aux, labor, mach = _HDPE_DN_TABLE[dn]
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[HDPE排水管·{dn}]主材{main:.1f}+人工{labor:.0f}"
        return None, ""
    
    # UPVC 排水管（粘接连接；人工明显高于同径 PPR 给水管，单独口径）
    if re.search(r"排水管", text) and re.search(r"UPVC|PVC-U|PVC", text):
        dn = _extract_dn_for_table(name, feature, _UPVC_DRAIN_DN_TABLE)
        if dn:
            main, labor, aux_mach = _UPVC_DRAIN_DN_TABLE[dn]
            aux = round(aux_mach * 0.85, 2)
            mach = round(aux_mach - aux, 2)
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[UPVC排水管·{dn}]主材{main:.1f}+人工{labor:.0f}"
        return None, ""

    # UPVC 冷凝水管（粘接连接，含接头管件+保温，人工低）
    if re.search(r"冷凝水管|冷凝排水管|冷凝水", text):
        dn = _extract_dn_for_table(name, feature, _UPVC_CONDENSATE_DN_TABLE)
        if dn:
            main, aux, labor, mach = _UPVC_CONDENSATE_DN_TABLE[dn]
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[UPVC冷凝水管·{dn}]主材{main:.1f}+人工{labor:.0f}"
    
    # PPR / 给排水管：按特征"含管道配件"区分口径
    #   口径 A（含管道配件）：主材含管件、辅材≈主材×0.5、人工≈口径B×0.45（深圳开市客等）
    #   口径 B（纯管材）：主材=纯管材价、人工高（珠海会所等）
    if re.search(r"管道配件|管件|接头管件", text):
        dn = _extract_dn_for_table(name, feature, _PIPE_FITTING_DN_TABLE)
        if not dn:
            dn = _extract_dn_for_table(name, feature, _PIPE_DN_TABLE)
        if dn:
            if dn in _PIPE_FITTING_DN_TABLE:
                main, aux, labor, mach = _PIPE_FITTING_DN_TABLE[dn]
            else:
                main, labor, aux_mach = _PIPE_DN_TABLE[dn]
                aux = round(aux_mach * 0.85, 2)
                mach = round(aux_mach - aux, 2)
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[塑料管含管件·{dn}]主材{main:.1f}+人工{labor:.0f}"
        return None, ""
    
    # 口径 B（无"含管道配件"字样）
    dn = _extract_dn_for_table(name, feature, _PIPE_DN_TABLE)
    if not dn:
        return None, ""
    
    main, labor, aux_mach = _PIPE_DN_TABLE[dn]
    # DN50区分：热给水管(保温)47.10 vs 普通给水管15.0（实际样本校准）
    if dn == "DN50" and not re.search(r"热给水|热水", text):
        main, labor, aux_mach = 15.0, 24.0, 1.5
    aux = round(aux_mach * 0.85, 2)
    mach = round(aux_mach - aux, 2)
    return {
        "material_main": main,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": labor,
        "machinery": mach,
    }, f"[塑料管拆价·{dn}]主材{main:.1f}+人工{labor:.0f}"
