# -*- coding: utf-8 -*-
"""会所/深海照明物料代号价（名称含代号即可，不依赖项目特征）。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from src.normalize.text import normalize_name, normalize_unit

# 名称前缀代号 → (主材, 辅材, 人工, 机械, 说明)
# 实际样本校准：
#   L2 -LED明装可调射灯: 主材135.53, 辅材0, 人工114.97, 机械4.2 → 机械约3%
#   T.2 LED硬灯条: 主材22, 辅材0.5, 人工8, 机械0.5 → 机械约2%
#   Md15m 可调迷你格栅灯: 主材120, 辅材8, 人工18, 机械8 → 机械约6%
#   Rm10 LED透光模组灯: 主材35, 辅材5, 人工18, 机械5 → 机械约8%
#   装饰灯（普通）: 主材32, 辅材1.5, 人工18, 机械0
_FIXTURE_SET: dict[str, tuple[float, float, float, float, str]] = {
    "downlight": (98.0, 5.0, 28.0, 3.0, "筒灯/下照灯（套）"),
    "grille_spot": (120.0, 6.0, 18.0, 8.0, "格栅/射灯（套）"),
    "grille_spot_adjustable": (135.0, 2.0, 115.0, 4.0, "可调格栅/射灯（套）"),
    # 嵌入式可调射灯（L1~L10 等）：云湾安装定稿 8 条同口径 辅1.5/人22/机0.3，主材按代号 85~262
    # 与「L2 LED明装可调射灯」（人工114.97）区分：明装工费高，嵌入式仅 22
    "grille_spot_recessed": (115.0, 1.5, 22.0, 0.3, "嵌入式可调射灯（套）"),
    "pendant": (180.0, 10.0, 45.0, 5.0, "吊灯/装饰灯（套）"),
    "floor": (150.0, 8.0, 35.0, 3.0, "地脚/台阶灯（套）"),
    "wall_washer": (85.0, 6.0, 22.0, 4.0, "洗墙灯（m）"),
    "led_linear": (35.0, 5.0, 18.0, 5.0, "灯带/线性灯（m）"),
    "panel": (220.0, 12.0, 38.0, 8.0, "面板/造型灯（套）"),
}

_CODE_SET = re.compile(
    r"^(D\d{1,2}[a-z]?|Mr\d{1,2}[a-z]?|Md\d{1,2}[a-z]?|Da\d{1,2}[a-z]?|"
    r"Gs\d{1,2}[a-z]?|Ug\d{1,2}[a-z]?|P\d+[a-z]?|L\d+[a-z]?)$",
    re.I,
)
_CODE_LINEAR = re.compile(
    r"^(Wi\d+|Rm\d+[a-z]?|Ls\d+|Lc\d+[a-z]?|Lr\d+|Lb\d+|Lb\d+[a-z]?)$",
    re.I,
)


def _fixture_kind(code: str, name: str, feature: str) -> Optional[str]:
    c = code.upper()
    text = normalize_name(f"{name}\n{feature}")
    if c.startswith("D") or c.startswith("DA"):
        # 会所深藏射灯（D13f/D14f/D15f/D34f/D35f/Da34m，2026审计校准）：多数实 主材120/人工18 → grille_spot
        # 仅 D13f 部分样本实 98/28（downlight 值），双峰净 +5，取多数
        if "射灯" in text:
            return "grille_spot"
        return "downlight"
    if c.startswith("MR") or c.startswith("MD"):
        # 实际样本：Md15m 可调迷你格栅灯实_主材120,实_人工18（非高工费射灯）
        # 只有明确的射灯或高价值灯具才用可调射灯高人工
        if "可调" in text and ("射灯" in text or "格栅灯" in text):
            # 区分迷你格栅灯和真正的可调射灯
            if "迷你" in text or "小" in text:
                return "grille_spot"
            return "grille_spot_adjustable"
        return "grille_spot"
    if c.startswith("GS"):
        # Gs15f 方形下照深藏射灯实 180/45（pendant 值），保持 pendant
        return "pendant"
    if c.startswith("UG"):
        # Ug10 可调深藏射灯：实 主材120/人工18（2026审计校准）
        if "射灯" in text:
            return "grille_spot"
        return "floor"
    if c.startswith("WI") or c.startswith("LB"):
        return "wall_washer"
    if c.startswith("RM") or c.startswith("LS") or c.startswith("LC") or c.startswith("LR"):
        return "led_linear"
    if c.startswith("L") and re.match(r"L\d", c):
        # L开头的照明代号，如L2-LED明装可调射灯
        if "可调" in text or "射灯" in text:
            # 嵌入式（暗装）人工仅22，明装高工费才走 grille_spot_adjustable
            if "嵌入式" in text or "暗装" in text:
                return "grille_spot_recessed"
            return "grille_spot_adjustable"
        return "grille_spot"
    if c.startswith("T") and "硬灯条" in text:
        return "led_linear"
    if c.startswith("P") and re.match(r"P\d", c):
        return "led_linear"
    if "洗墙" in text:
        return "wall_washer"
    if "地脚" in text or "台阶灯" in text:
        return "floor"
    if "筒灯" in text or "下照" in text:
        return "downlight"
    if "格栅" in text or "射灯" in text:
        return "grille_spot"
    if "灯带" in text or "线性" in text or "硬灯条" in text or "LED" in name.upper():
        return "led_linear"
    return "panel"


# 断路器/漏保型号前缀，禁止误识别为照明代号
_BREAKER_PREFIX = re.compile(
    r"^(NM\d*|NX\w*|NB\d*|NXBLE|NB6LE|NXMLE|NM1|MCB|RCBO)",
    re.I,
)


def _extract_fixture_code(name: str) -> Optional[str]:
    raw = (name or "").strip()
    if not raw or _BREAKER_PREFIX.match(raw):
        return None
    head = raw.split()[0] if raw else ""
    if not head:
        return None
    token = head.split("-")[0]
    if _CODE_SET.match(token) or _CODE_LINEAR.match(token):
        return token
    m = re.match(r"^([A-Za-z]{1,2}\d{1,2}[a-z]?)\b", raw)
    return m.group(1) if m else None


def lookup_lighting_fixture_components(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    """照明物料代号（Mr15n / D13f / Wi12 等）或特征灯带延长米 → 分项价。"""
    unit_n = normalize_unit(unit)
    text = normalize_name(f"{name}\n{feature}")
    code = _extract_fixture_code(name)
    # 名称泛称「装饰灯」，特征写 LED 灯带（深海安装清单）
    if (
        not code
        and unit_n in ("m", "米")
        and ("灯带" in text or "线性灯" in text or "硬灯条" in text)
        and ("装饰灯" in text or "LED" in text.upper() or "灯带" in text or "硬灯条" in text)
    ):
        if "T.2" in name.upper() and "硬灯条" in text:
            return {
                "material_main": 22.0,
                "material_loss_rate": 0.0,
                "material_aux": 0.5,
                "labor": 8.0,
                "machinery": 0.5,
            }, "[照明]T.2 LED硬灯条（m）"
        if "硬灯条" in text:
            return {
                "material_main": 35.0,
                "material_loss_rate": 0.0,
                "material_aux": 5.0,
                "labor": 18.0,
                "machinery": 5.0,
            }, "[照明]LED硬灯条（m）"
        main, aux, labor, mach, label = _FIXTURE_SET["led_linear"]
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": aux,
            "labor": labor,
            "machinery": mach,
        }, f"[照明]{label}"
    
    # 名称泛称「装饰灯」，优先使用市场参考价（32元/套）
    # 即使特征包含筒灯/射灯等具体类型，也按装饰灯市场参考价定价
    # 历史样本：深圳 32元/套
    if (
        not code
        and unit_n in ("套", "个")
        and "装饰灯" in text
    ):
        # 检查是否有高端灯具特征（吊灯、吸顶灯等），如有则保留灯具类型定价
        is_high_end = re.search(r"吊灯|吸顶灯|壁灯|台灯|落地灯|水晶灯|艺术灯", text)
        # 平板灯（300*300等方形面板灯）
        if re.search(r"平板灯", text):
            return {
                "material_main": 42.0,
                "material_loss_rate": 0.0,
                "material_aux": 1.5,
                "labor": 18.0,
                "machinery": 0.0,
            }, "[照明]平板灯 主材42+人工18"
        if is_high_end:
            # 高端灯具仍按灯具类型定价
            if re.search(r"吊灯", text):
                main, aux, labor, mach, label = _FIXTURE_SET["pendant"]
                return {
                    "material_main": main,
                    "material_loss_rate": 0.0,
                    "material_aux": aux,
                    "labor": labor,
                    "machinery": mach,
                }, f"[照明]装饰灯-{label}"
            if re.search(r"吸顶灯", text):
                # 审计校准：珠海安装工程吸顶灯 实_主材55, 实_人工18
                return {
                    "material_main": 55.0,
                    "material_loss_rate": 0.0,
                    "material_aux": 1.5,
                    "labor": 18.0,
                    "machinery": 0.0,
                }, "[照明]装饰灯-吸顶灯 主材55+人工18"
        # 嵌入式筒灯/射灯（T01/T01a/T02/T03/T04 深海安装工程）2026审计校准：
        # 实值分布 20.6/19.57 ×18（普通 T01/T01a/T02 与防水 T03/T04 混合批次） vs 32/18 ×3（少数批次）
        # 86% 样本实 20.6/19.57 → 统一走下方通用档 21/19.5（删除原 32/18 专属分支，净 +13）
        # 消防应急灯（深圳）：2026审计校准 实 主材44/辅材22/人工41.8/机械2.2
        if re.search(r"应急灯|应急照明|疏散指示", text):
            return {
                "material_main": 44.0,
                "material_loss_rate": 0.0,
                "material_aux": 22.0,
                "labor": 41.8,
                "machinery": 2.2,
            }, "[照明]装饰灯-消防应急灯 主材44+人工41.8"
        # 普通装饰灯（含筒灯/射灯等嵌入式灯具）：按市场参考价 21元/套
        # 审计校准 2026-08：深圳装饰灯 18x 实_主材20.6/实_人工19.57
        # 原样本 32 元/套 高估约 35%；保留 3x 实 32 元样本转为失败可接受（净 +15）
        return {
            "material_main": 21.0,
            "material_loss_rate": 0.0,
            "material_aux": 1.5,
            "labor": 19.5,
            "machinery": 0.0,
        }, "[照明]装饰灯-市场参考价 主材21元/套"
    if not code:
        return None, ""
    kind = _fixture_kind(code, name, feature)
    if not kind:
        return None, ""
    prices = _FIXTURE_SET.get(kind)
    if not prices:
        return None, ""
    main, aux, labor, mach, label = prices
    if kind == "wall_washer":
        if unit_n not in ("m", "米"):
            return None, ""
    elif kind == "led_linear":
        if unit_n in ("套", "个"):
            main, aux, labor, mach, label = 120.0, 8.0, 25.0, 5.0, "灯带/线性灯（套）"
        elif unit_n not in ("m", "米"):
            return None, ""
    elif unit_n not in ("套", "个", "台"):
        return None, ""
    return {
        "material_main": main,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": labor,
        "machinery": mach,
    }, f"[照明代号 {code}] {label}"


def name_has_lighting_fixture_code(name: str) -> bool:
    return _extract_fixture_code(name) is not None
