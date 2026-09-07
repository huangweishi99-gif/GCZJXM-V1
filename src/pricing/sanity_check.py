# -*- coding: utf-8 -*-
"""价格合理性校验层（兜底价数量级防线）。

用途：
1. 任何来源（历史/市场参考/工艺定额）给出的人材机单价，在写入结果前做数量级校验；
2. 命中"不合理价"（如勾缝剂 0.08 元/kg、人工 120 元/工日）时，打标 + 降级 auto_fill，
   把"静默错误"变成"需人工确认"；
3. 提供 `audit-price` 命令扫描整库（市场参考价、定额内嵌价、历史事实价）。

基准：
- 单位价格常识区间（按材料类别/单位，2026 市场口径）；
- config/market_reference_prices.json 同规则聚合区间（动态）；
- config/shenzhen_price_info_2023.json 信息价区间（动态）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# 1. 静态常识价格区间：material_keyword -> (min, max, unit, 说明)
#    数量级校验，min/max 取宽口径（3~5 倍余量），只拦明显数量级错误。
# ---------------------------------------------------------------------------
PRICE_BANDS: Dict[str, Tuple[float, float, str, str]] = {
    # 胶/粉/浆类（元/kg）
    "云石胶": (8, 40, "元/kg", "云石胶"),
    "石材胶": (8, 40, "元/kg", "石材胶"),
    "粘结剂": (5, 30, "元/kg", "粘结剂"),
    "粘合剂": (5, 30, "元/kg", "粘合剂"),
    "瓷砖胶": (2, 10, "元/kg", "瓷砖胶"),
    "勾缝剂": (3, 15, "元/kg", "勾缝剂"),
    "填缝剂": (3, 15, "元/kg", "填缝剂"),
    "白水泥": (300, 800, "元/t", "白水泥"),
    "腻子": (0.8, 3.5, "元/kg", "成品腻子"),
    "腻子粉": (0.8, 3.5, "元/kg", "成品腻子粉"),
    "石膏粉": (0.8, 3.5, "元/kg", "石膏粉"),
    "乳胶漆": (10, 35, "元/kg", "乳胶漆"),
    "涂料": (8, 40, "元/kg", "涂料"),
    "底漆": (8, 30, "元/kg", "底漆"),
    "面漆": (10, 35, "元/kg", "面漆"),
    "稀释剂": (5, 20, "元/kg", "稀释剂"),
    "稀料": (5, 20, "元/kg", "稀料"),
    "防水涂料": (12, 45, "元/kg", "防水涂料"),
    "防锈漆": (6, 20, "元/kg", "防锈漆"),
    "密封胶": (8, 35, "元/kg", "密封胶"),
    "玻璃胶": (8, 35, "元/kg", "玻璃胶"),
    "壁纸胶": (8, 30, "元/kg", "壁纸胶"),
    "胶水": (6, 30, "元/kg", "胶水"),
    "结晶粉": (10, 40, "元/kg", "石材结晶粉"),
    "抛光剂": (12, 45, "元/kg", "抛光剂"),
    "抛光粉": (10, 40, "元/kg", "抛光粉"),
    # 砂石/水泥（元/t 或 元/m³）—— 更具体的词放前面，避免"水泥"误吞"水泥砂浆"
    "水泥砂浆": (120, 400, "元/m³", "水泥砂浆"),
    "水泥": (300, 800, "元/t", "水泥"),
    "中砂": (80, 220, "元/m³", "中砂"),
    "细砂": (80, 220, "元/m³", "细砂"),
    "砂浆": (120, 400, "元/m³", "预拌砂浆"),
    # 五金（元/套、元/个、元/kg）
    "干挂件": (2, 12, "元/套", "干挂件"),
    "膨胀螺栓": (0.5, 3, "元/套", "膨胀螺栓"),
    "自攻螺钉": (0.03, 0.3, "元/个", "自攻螺钉"),
    "螺丝": (0.03, 0.3, "元/个", "螺丝"),
    "合页": (10, 80, "元/副", "合页"),
    "门锁": (40, 400, "元/套", "门锁"),
    "焊接材料": (4, 20, "元/kg", "焊材"),
    "钢丝棉": (1, 5, "元/块", "钢丝棉"),
    # 板材/型材（元/㎡ 或 元/m）
    "石膏板": (10, 40, "元/㎡", "石膏板"),
    "不锈钢龙骨": (15, 60, "元/m", "不锈钢龙骨"),
    "轻钢龙骨": (4, 16, "元/m", "轻钢龙骨"),
    "龙骨": (4, 16, "元/m", "龙骨"),
    "铝扣板": (30, 160, "元/㎡", "铝扣板"),
    "不锈钢": (15000, 40000, "元/t", "不锈钢板材"),
    # 主材面层（元/㎡）
    "地砖": (30, 300, "元/㎡", "地砖"),
    "面砖": (30, 300, "元/㎡", "面砖"),
    "墙砖": (30, 300, "元/㎡", "墙砖"),
    "石材": (80, 2000, "元/㎡", "石材"),
    "大理石": (100, 2000, "元/㎡", "大理石"),
    "花岗岩": (80, 1500, "元/㎡", "花岗岩"),
    # 门/窗/成品
    "木门": (150, 3000, "元/樘", "木门"),
    "铝合金窗": (150, 2000, "元/㎡", "铝合金窗"),
    "金属扶手": (80, 600, "元/m", "金属扶手"),
    "弯头": (5, 80, "元/个", "弯头"),
    # 水/成品
    "防水卷材": (15, 60, "元/㎡", "防水卷材"),
}

# 人工单价区间（元/工日，2026 市场口径，全成本含社保）
LABOR_BANDS = (200, 600)
# 机械台班单价区间（元/台班）
MACHINERY_BANDS = (50, 800)
# 综合单价合理区间（元/单位工程量，粗略兜底，只拦离谱值）
COST_BANDS = (0.5, 50000)


def check_material_price(name: str, price: float, unit: str = "") -> Tuple[bool, Optional[str]]:
    """单材料价格数量级校验。

    Returns:
        (ok, reason)；reason 非空表示越界说明（ok=False）或边界提示。
    """
    if not price or price <= 0:
        return False, f"材料[{name}]价格为 0 或负值"
    for kw, (lo, hi, _, desc) in PRICE_BANDS.items():
        if kw in name:
            if not (lo <= price <= hi):
                return False, f"材料[{name}]单价 {price} {unit} 超出{desc}合理区间({lo}~{hi} {unit})"
            return True, None
    return True, None


def check_labor_price(price: float, trade: str = "") -> Tuple[bool, Optional[str]]:
    if not price or price <= 0:
        return False, f"人工单价 {price} 为 0 或负值"
    if not (LABOR_BANDS[0] <= price <= LABOR_BANDS[1]):
        return False, f"人工单价 {price} 元/工日超出合理区间({LABOR_BANDS[0]}~{LABOR_BANDS[1]})"
    return True, None


def check_machinery_price(price: float) -> Tuple[bool, Optional[str]]:
    if not price or price <= 0:
        return False, f"机械台班单价 {price} 为 0 或负值"
    if not (MACHINERY_BANDS[0] <= price <= MACHINERY_BANDS[1]):
        return False, f"机械台班单价 {price} 元/台班超出合理区间({MACHINERY_BANDS[0]}~{MACHINERY_BANDS[1]})"
    return True, None


def check_cost_unit_price(price: float, unit: str = "") -> Tuple[bool, Optional[str]]:
    if price <= 0:
        return False, f"综合单价 {price} 为 0 或负值"
    if not (COST_BANDS[0] <= price <= COST_BANDS[1]):
        return False, f"综合单价 {price} {unit} 超出合理区间({COST_BANDS[0]}~{COST_BANDS[1]})"
    return True, None


# ---------------------------------------------------------------------------
# 2. 主材含量基准校验：m² 含量（元/㎡ 拆解防误）
#    material_keyword -> (min, max, unit, 说明)  消耗量区间
# ---------------------------------------------------------------------------
CONSUMPTION_BANDS: Dict[str, Tuple[float, float, str, str]] = {
    "乳胶漆": (0.20, 0.45, "kg/㎡", "面漆2遍净耗"),
    "涂料": (0.20, 0.50, "kg/㎡", "涂料净耗"),
    "腻子": (0.5, 3.0, "kg/㎡", "腻子2遍"),
    "腻子粉": (0.5, 3.0, "kg/㎡", "腻子2遍"),
    "瓷砖胶": (3.0, 8.0, "kg/㎡", "薄贴法"),
    "勾缝剂": (0.1, 1.0, "kg/㎡", "勾缝"),
    "防水涂料": (1.0, 3.0, "kg/㎡", "2遍涂刷"),
    "底漆": (0.10, 0.25, "kg/㎡", "底漆1遍"),
    "面漆": (0.20, 0.45, "kg/㎡", "面漆2遍"),
    "石材": (0.95, 1.15, "㎡/㎡", "含损耗"),
    "地砖": (0.95, 1.15, "㎡/㎡", "含损耗"),
    "面砖": (0.95, 1.15, "㎡/㎡", "含损耗"),
}


def check_consumption(name: str, amount: float, unit: str = "") -> Tuple[bool, Optional[str]]:
    """主材单耗数量级校验（针对 m² 类清单）。"""
    if amount <= 0:
        return True, None
    for kw, (lo, hi, u, desc) in CONSUMPTION_BANDS.items():
        if kw in name:
            if not (lo <= amount <= hi):
                return False, f"主材[{name}]单耗 {amount} {u or unit} 超出{desc}合理区间({lo}~{hi} {u})"
            return True, None
    return True, None


# ---------------------------------------------------------------------------
# 3. 组件整体校验（ComponentJudgment.components）
# ---------------------------------------------------------------------------
def check_components(comps: Dict[str, Any]) -> List[str]:
    """对人材机组件做整体数量级校验，返回越界原因列表（空=全部通过）。"""
    reasons: List[str] = []
    main_price = float(comps.get("material_main") or 0)
    aux_price = float(comps.get("material_aux") or 0)
    labor_price = float(comps.get("labor") or 0)
    mach_price = float(comps.get("machinery") or 0)

    # 人工：组件里 labor 是"元/单位工程量"，无法直接对照 元/工日，
    # 但如果单平米人工超过 300 元，说明疑似填了工日单价，提示。
    if labor_price and labor_price > 300:
        reasons.append(f"人工费 {labor_price} 元/单位工程量疑似过高（疑似误填工日单价）")

    # 机械同理
    if mach_price and mach_price > 300:
        reasons.append(f"机械费 {mach_price} 元/单位工程量疑似过高（疑似误填台班单价）")

    # 主材费不在此做硬性降级：高档石材/进口材料主材费 >2000 元/㎡ 属正常，
    # 组件层无法区分档次，交由 config 审计（材料单价/单耗）与人工复核。
    return reasons


def apply_sanity_flags(comps: Dict[str, Any], name: str) -> Dict[str, Any]:
    """对组件打标：把越界信息写入 notes/warnings，供上层降级。"""
    reasons = check_components(comps)
    if not reasons:
        return comps
    comps["sanity_reasons"] = reasons
    notes = comps.get("notes") or []
    for r in reasons:
        note = f"[价格校验] {r}"
        if note not in notes:
            notes.append(note)
    comps["notes"] = notes
    return comps


# ---------------------------------------------------------------------------
# 4. 全库审计：扫描配置/DB 中的价格事实，输出越界清单
# ---------------------------------------------------------------------------
def audit_market_reference(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """扫描 config/market_reference_prices.json 的规则价格。"""
    fp = Path(path) if path else ROOT / "config" / "market_reference_prices.json"
    issues: List[Dict[str, Any]] = []
    if not fp.exists():
        return issues
    data = json.loads(fp.read_text(encoding="utf-8"))
    rules = data.get("rules", [])
    for rule in rules:
        price = float(rule.get("unit_price") or 0)
        if price <= 0:
            continue
        ok, reason = check_material_price(str(rule.get("name") or ""), price)
        if not ok:
            issues.append({
                "source": "market_reference",
                "name": rule.get("name"),
                "price": price,
                "issue": reason,
                "confidence": rule.get("confidence"),
            })
    return issues


def audit_quota_prices(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """扫描 config/quota_standards.json 内嵌材料价。"""
    fp = Path(path) if path else ROOT / "config" / "quota_standards.json"
    issues: List[Dict[str, Any]] = []
    if not fp.exists():
        return issues
    data = json.loads(fp.read_text(encoding="utf-8"))
    for item in data.get("quota_items", []):
        for mat_name, mat_data in (item.get("materials") or {}).items():
            if len(mat_data) < 4:
                continue
            price = float(mat_data[2])
            ok, reason = check_material_price(str(mat_name), price)
            if not ok:
                issues.append({
                    "source": "quota_standards",
                    "quota_code": item.get("quota_code"),
                    "name": mat_name,
                    "price": price,
                    "issue": reason,
                })
    return issues


def audit_labor_rates(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """扫描 config/labor_rates.json 人工/机械单价。"""
    fp = Path(path) if path else ROOT / "config" / "labor_rates.json"
    issues: List[Dict[str, Any]] = []
    if not fp.exists():
        return issues
    data = json.loads(fp.read_text(encoding="utf-8"))
    default = data.get("default", {})
    cands = []
    if default.get("labor_unit_price"):
        cands.append(("default", "", default["labor_unit_price"]))
    if default.get("machinery_unit_price"):
        cands.append(("default_mach", "", default["machinery_unit_price"]))
    for city, cfg in (data.get("cities") or {}).items():
        if cfg.get("labor_unit_price"):
            cands.append((city, "", cfg["labor_unit_price"]))
        if cfg.get("machinery_unit_price"):
            cands.append((f"{city}_mach", "", cfg["machinery_unit_price"]))
        for trade, price in (cfg.get("trades") or {}).items():
            cands.append((f"{city}.{trade}", trade, price))
    for label, trade, price in cands:
        price = float(price)
        if price <= 0:
            continue
        if trade:
            ok, reason = check_labor_price(price, trade)
            issue_type = "labor"
        elif label.endswith("_mach"):
            ok, reason = check_machinery_price(price)
            issue_type = "machinery"
        else:
            ok, reason = check_labor_price(price)
            issue_type = "labor"
        if not ok:
            issues.append({
                "source": "labor_rates",
                "name": label,
                "price": price,
                "issue": reason,
                "type": issue_type,
            })
    return issues


def run_full_audit() -> Dict[str, Any]:
    """运行全部价格审计，汇总报告。"""
    report = {
        "market_reference": audit_market_reference(),
        "quota_standards": audit_quota_prices(),
        "labor_rates": audit_labor_rates(),
    }
    report["total_issues"] = sum(len(v) for v in report.values())
    return report
