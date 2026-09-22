# -*- coding: utf-8 -*-
"""装饰条形风口：按规格长度×宽度档计延长米价（深海定稿口径）。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from src.normalize.text import normalize_name, normalize_unit

# 元/延长米（清单单位为「个」时 × 长度；单位为「m」时即为单价）
# 大型装饰风口（宽>200mm）单价更高
# 实际样本校准：
#   1200*150mm: 实_total≈91, 延长米1.2m → 75.8元/m
#   1640*200mm: 实_total≈164, 延长米1.64m → 100元/m
#   4110*150mm: 实_total≈308, 延长米4.11m → 74.9元/m
_RATE_BY_WIDTH_MM = (
    (160, 75.0),    # 150mm宽及以下（实际样本：150mm宽约75元/m）
    (200, 100.0),   # 200mm宽（实际样本：200mm宽约100元/m；深圳送风口分0.70/0.30与0.75/0.20两批，保持100元/m中性）
    (300, 180.0),   # 大型装饰风口（宽200-300mm）
    (9999, 250.0),  # 特大型装饰风口（宽>300mm）
)

# 普通长条风口（单层百叶/矩形送回风口等，规格 L×W 且 L/W≥2.5）：按延长米×宽档计价（total 元/m）
# 实际样本拟合：
#   云湾矩形送(回)风口: 100宽≈77, 150宽≈93~100, 200宽≈115~120
#   学校单层百叶150宽:  90~115（综合~100）
#   理想汽车送回风口:   250宽≈140, 300宽≈165（该批为框架样本，仅供参考）
_COMMON_STRIP_RATE_BY_WIDTH_MM = (
    (100, 80.0),
    (160, 100.0),
    (200, 120.0),
    (300, 168.0),
    (9999, 220.0),
)


def _common_strip_rate_per_meter(width_mm: int) -> float:
    for limit, rate in _COMMON_STRIP_RATE_BY_WIDTH_MM:
        if width_mm <= limit:
            return rate
    return _COMMON_STRIP_RATE_BY_WIDTH_MM[-1][1]


def _parse_length_width_mm(text: str) -> Tuple[Optional[int], Optional[int]]:
    """从「规格/型号」字段解析 L×W（mm）；避免与后续清单序号粘连如 150\\n4.。"""
    for prefix in ("规格", "型号"):
        m = re.search(
            rf"{prefix}[:：][^\n]*?(\d{{3,6}})\s*[*×xX]\s*(\d{{2,4}})",
            text,
            re.I,
        )
        if not m:
            continue
        length_mm, width_mm = int(m.group(1)), int(m.group(2))
        while width_mm > 400 and width_mm >= 10:
            width_mm //= 10
        if 200 <= length_mm <= 120_000 and 80 <= width_mm <= 400:
            return length_mm, width_mm
    return None, None


def _rate_per_meter(width_mm: int) -> float:
    for limit, rate in _RATE_BY_WIDTH_MM:
        if width_mm <= limit:
            return rate
    return _RATE_BY_WIDTH_MM[-1][1]


def lookup_decorative_diffuser_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """条形装饰风口：清单按「个」套总长，或按「m」走延长米单价。"""
    unit_n = normalize_unit(unit)
    text = normalize_name(f"{name}\n{feature}")
    
    if "静压箱" in text:
        m = re.search(r"(\d{2,4})\s*[*×xX]\s*(\d{2,4})", text)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            depth_match = re.search(r"H[=:]\s*(\d{2,4})", text)
            depth = int(depth_match.group(1)) if depth_match else 200
            volume_liters = (w * h * depth) / 1_000_000
            # 管道消声静压箱价格较高，按体积分级定价
            is_noise = "消声" in text or "管道" in text
            if is_noise:
                # 消声静压箱价格更高（含消声棉、吸声板等）
                if volume_liters <= 60:
                    main, labor = 330.0, 313.0
                elif volume_liters <= 120:
                    main, labor = 450.0, 400.0
                elif volume_liters <= 200:
                    main, labor = 600.0, 500.0
                else:
                    main, labor = 800.0, 650.0
                aux = round((main + labor) * 0.5, 2)
                mach = round((main + labor) * 0.05, 2)
            else:
                # 普通静压箱（实际样本校准）
                # 风口静压箱500*500（H=300）: volume=75L, 实_主材99.58, 实_人工94.61, 辅材49.79, 机械4.98 → total≈249
                if volume_liters <= 60:
                    main, labor = 85.0, 80.0
                elif volume_liters <= 120:
                    main, labor = 100.0, 95.0
                elif volume_liters <= 200:
                    main, labor = 150.0, 120.0
                else:
                    main, labor = 200.0, 160.0
                aux = round((main + labor) * 0.25, 2)
                mach = round((main + labor) * 0.025, 2)
            return {
                "material_main": main,
                "material_loss_rate": 0.03,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[静压箱] {w}×{h}×{depth}mm"
        # 默认消声静压箱
        main, labor = 330.0, 313.0
        aux = round((main + labor) * 0.5, 2)
        mach = round((main + labor) * 0.05, 2)
        return {
            "material_main": main,
            "material_loss_rate": 0.03,
            "material_aux": aux,
            "labor": labor,
            "machinery": mach,
        }, "[静压箱] 默认规格（消声）"
    
    if "装饰风口" not in text and "条形" not in text and "风口" not in name:
        return None, ""

    # 整项拆除/恢复（名称含"风口"仅为罗列，如"灯具、烟感、…风口…拆除及恢复"）
    # 不是风口行，交由拆除/特殊行剖面处理，避免按 100 元/个 误判整项
    if unit_n in ("项", "系统", "宗") and ("拆除" in text or "恢复" in text):
        return None, ""

    # 只有装饰风口或条形风口才尝试解析规格尺寸；
    # 普通风口（单层百叶/送回风口等）若规格为"长条"（L×W 且 L/W≥2.5）也按规格计价，
    # 方形/圆形风口不套用延长米线性（其价格形态不同，维持默认档）
    is_plain_strip = False
    if "装饰风口" in text or "条形" in text:
        length_mm, width_mm = _parse_length_width_mm(f"{name}\n{feature}")
    else:
        length_mm, width_mm = None, None
        if "风口" in name and ("规格" in text or "型号" in text):
            if "圆形" not in text and not re.search(r"\bR\d{3,}", text):
                lm, wm = _parse_length_width_mm(f"{name}\n{feature}")
                if lm and wm and lm / max(wm, 1) >= 2.5:
                    length_mm, width_mm = lm, wm
                    is_plain_strip = True
    
    # ㎡单位处理（大面积风口或综合）
    if unit_n in ("㎡", "m2"):
        # 空调风口综合单价（审计校准 2026-08：深圳空调风口 9x 实_主材463.49/实_人工123.59）
        # total≈552 → 主材占比约84%（463.49/552）、人工占比约22%（123.59/552）
        total = 552.0
        main = round(total * 0.84, 2)
        labor = round(total * 0.22, 2)
        aux = round(total * 0.12, 2)
        mach = round(total * 0.001, 2)
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": aux,
            "labor": labor,
            "machinery": mach,
        }, "[空调风口·㎡] 综合单价552元/㎡"
    
    if not width_mm:
        if "条形" in text:
            m = re.search(r"(\d{2,3})mm", text)
            if m:
                width_mm = int(m.group(1))
                if width_mm < 80:
                    width_mm = None
        if not width_mm and ("送回风口" in text or "风口" in name and not "装饰风口" in text and not "条形" in text):
            # 普通空调风口（按实际样本修正）
            if "排风口" in text or "百叶排风" in text:
                # 排风口价格较低（实际样本：单层百叶排风口实_主材17.49,实_人工7.51 → total≈25）
                # 实际辅材1.63，机械1.63
                total = 25.0
                main = round(total * 0.70, 2)
                labor = round(total * 0.30, 2)
                aux = round(total * 0.065, 2)
                mach = round(total * 0.065, 2)
            elif "常开百叶" in text:
                # 常开百叶风口（消防联动型）: 实_主材200-261,实_人工80-100
                total = 340.0
                main = round(total * 0.77, 2)
                labor = round(total * 0.18, 2)
                aux = round(total * 0.03, 2)
                mach = round(total * 0.02, 2)
            elif "送回风口" in text:
                # 送回风口（实际样本：实_主材119, 实_人工32, 辅材7.94, 机械0 → total≈159）
                total = 150.0
                main = round(total * 0.76, 2)
                labor = round(total * 0.21, 2)
                aux = round(total * 0.05, 2)
                mach = 0.0
            else:
                # 普通风口（实际样本：实_主材75.43, 实_人工20.11, 辅材5.72, 机械0 → total≈100）
                total = 100.0
                main = round(total * 0.75, 2)
                labor = round(total * 0.20, 2)
                aux = round(total * 0.06, 2)
                mach = 0.0
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[空调风口·默认] {'排风口' if '排风口' in text else ('送回风口' if '送回风口' in text else '普通风口')}{total}元/个"
        if not width_mm:
            # 装饰风口但没有解析到尺寸，使用默认定价
            if "装饰风口" in text:
                # 实际样本：装饰风口实_主材71.89,实_人工19.17,辅材4.79,机械0 → total≈96
                total = 96.0
                main = round(total * 0.75, 2)
                labor = round(total * 0.20, 2)
                aux = round(total * 0.05, 2)
                mach = 0.0
                return {
                    "material_main": main,
                    "material_loss_rate": 0.0,
                    "material_aux": aux,
                    "labor": labor,
                    "machinery": mach,
                }, "[空调风口·默认] 装饰风口96元/个"
            return None, ""
    rate = _common_strip_rate_per_meter(width_mm) if is_plain_strip else _rate_per_meter(width_mm)

    # 单位为延长米：综合单价 = 档位元/m
    if unit_n in ("m", "米"):
        # 条形空调风口特殊定价（实际样本：150mm实_主材63.75,实_人工30,辅材2.5,机械0.2 → total≈96）
        if "条形" in text:
            total = 96.0
            main = round(total * 0.66, 2)
            labor = round(total * 0.31, 2)
            aux = round(total * 0.027, 2)
            mach = round(total * 0.002, 2)
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[条形空调风口·宽{width_mm}mm] 默认96元/m"
        total = rate
        note = f"[装饰风口·宽{width_mm}mm]{rate:.1f}元/m"
    elif unit_n in ("个", "套"):
        if not length_mm:
            # 单个风口按默认价格（根据宽度和类型分类）
            if "条形" in text:
                # 条形空调风口（实际样本：150mm实_主材63.75,实_人工30 → total≈94, 人工占比32%）
                total = 94.0
                main = round(total * 0.68, 2)
                labor = round(total * 0.30, 2)
                aux = round(total * 0.02, 2)
                mach = round(total * 0.01, 2)
                return {
                    "material_main": main,
                    "material_loss_rate": 0.0,
                    "material_aux": aux,
                    "labor": labor,
                    "machinery": mach,
                }, f"[条形空调风口·宽{width_mm}mm] 默认94元/个"
            else:
                total = 180.0
                main = round(total * 0.67, 2)
                labor = round(total * 0.27, 2)
                aux = round(total * 0.04, 2)
                mach = round(total * 0.02, 2)
                return {
                    "material_main": main,
                    "material_loss_rate": 0.0,
                    "material_aux": aux,
                    "labor": labor,
                    "machinery": mach,
                }, "[空调风口·单个] 默认180元/个"
        total = round(length_mm / 1000.0 * rate, 4)
        note = (
            f"[装饰风口·{length_mm}×{width_mm}mm]"
            f"延长米{length_mm/1000:.3f}m×{rate:.1f}元/m"
        )
    else:
        return None, ""

    # 大型装饰风口人工占比调整（实际样本校准）
    # 装饰风口1200*150mm: 实_主材71.89,实_人工19.17,辅材4.79,机械0 → total≈96（小尺寸）
    # 装饰风口1640*200mm: 实_主材114.80,实_人工49.20,辅材4.92,机械0 → total≈175（中号）
    # 装饰风口4110*150mm: 实_主材215.78,实_人工92.47,辅材9.25,机械0 → total≈317（大号）
    # 装饰风口（大型966+414）: 实_辅材41.4,机械0 → total≈1421
    # 注：深圳200宽条形风口分0.70/0.30与0.75/0.20两批（特征相同），本模块按大尺寸0.67-0.69/0.28-0.29命中0.70/0.30批，
    #     0.75/0.20批（人工占比低）暂无法区分，保持原档位避免批量回归。
    # 辅材占比：小尺寸约5%，中大号约3-4%
    if total > 500:
        main_ratio = 0.67
        labor_ratio = 0.29
        aux_ratio = 0.04
    elif total > 200:
        # 2026-09-14 审计校准：深圳 200mm 宽装饰风口（4470/4040/2640×200）此档内实为两批，
        # 多数派（3:1）为 主0.75/人0.20/辅0.05（实 357/95、322.7/86.1、210.9/56.2），
        # 少数派（4040×200 同规格 282.8/121.2）为 0.68/0.29/0.03 且与多数派同规格共存、无法区分。
        # 取多数派：净 +2；新旧比例和均为 1.00，合价不变，不影响校准。
        main_ratio = 0.75
        labor_ratio = 0.20
        aux_ratio = 0.05
    elif total > 100:
        # 审计校准：2000×150 单层百叶风口 实_主材132.3/实_人工45 → 人工占比约0.25
        main_ratio = 0.70
        labor_ratio = 0.25
        aux_ratio = 0.03
    else:
        main_ratio = 0.75
        labor_ratio = 0.20
        aux_ratio = 0.05
    
    main = round(total * main_ratio, 2)
    labor = round(total * labor_ratio, 2)
    aux = round(total * aux_ratio, 2)
    mach = 0.0
    return {
        "material_main": main,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": labor,
        "machinery": mach,
    }, note
