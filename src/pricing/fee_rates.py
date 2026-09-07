# -*- coding: utf-8 -*-
"""取费标准库：综合单价 = 人材机成本 × (1+管理费率+利润率+风险费率)。

综合单价构成（GB50500-2013）：
    综合单价 = 人工费 + 材料费 + 机械费 + 管理费 + 利润 + 风险费
             = 成本单价 × (1 + 管理费率 + 利润率 + 风险费率)

费率来源：config/fee_rates.json（按 工程类别×档位 建议，可人工覆盖）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).parent.parent.parent

DEFAULT_RATES: Dict[str, float] = {
    "management_fee_rate": 0.08,
    "profit_rate": 0.05,
    "risk_rate": 0.01,
    "safety_civil_rate": 0.021,
    "organization_fee_rate": 0.015,
    "tax_rate": 0.09,
}


def load_fee_rates(path: Optional[str] = None) -> Dict[str, Any]:
    """读取取费配置（合并 default + by_category + by_tier）。"""
    fp = Path(path) if path else ROOT / "config" / "fee_rates.json"
    if not fp.exists():
        return {"default": dict(DEFAULT_RATES)}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {"default": dict(DEFAULT_RATES)}


def get_rates(
    category: str = "",
    tier: str = "mid",
    path: Optional[str] = None,
    style: str = "",
) -> Dict[str, float]:
    """取综合单价费率建议。

    Args:
        category: 工程类别（装饰装修/土建/安装/幕墙/市政），未知走 default
        tier: 档位（high/mid/low）
        style: 项目风格（如 batch_fitout 批量精装 12%），优先级最高

    Returns:
        {management_fee_rate, profit_rate, risk_rate, ...}
    """
    cfg = load_fee_rates(path)
    rates: Dict[str, float] = dict(cfg.get("default", DEFAULT_RATES))

    # 合并顺序：default → tier（档位） → category（工程类别） → style（项目风格优先）
    by_tier = cfg.get("by_tier", {})
    tier_key = (tier or "mid").lower()
    if tier_key in by_tier:
        rates.update(by_tier[tier_key])

    by_cat = cfg.get("by_category", {})
    if category and category in by_cat:
        rates.update(by_cat[category])

    by_style = cfg.get("by_style", {})
    if style and style in by_style:
        rates.update(by_style[style])

    return rates


def apply_fees(
    cost_unit_price: float,
    category: str = "",
    tier: str = "mid",
    path: Optional[str] = None,
    style: str = "",
) -> Dict[str, float]:
    """在成本单价基础上计取 管理费+利润+风险，得到综合单价。

    Returns:
        {management_fee, profit, risk, comprehensive_unit_price}
    """
    rates = get_rates(category, tier, path, style)
    mgmt = cost_unit_price * rates["management_fee_rate"]
    profit = cost_unit_price * rates["profit_rate"]
    risk = cost_unit_price * rates["risk_rate"]
    return {
        "management_fee": round(mgmt, 2),
        "profit": round(profit, 2),
        "risk": round(risk, 2),
        "comprehensive_unit_price": round(cost_unit_price + mgmt + profit + risk, 2),
        "rates": rates,
    }


def build_summary(
    cost_unit_price: float,
    quantity: float,
    category: str = "",
    tier: str = "mid",
    path: Optional[str] = None,
    style: str = "",
) -> Dict[str, Any]:
    """生成单位工程费用汇总（分部分项 → 措施 → 规费 → 税金 → 含税总价）。"""
    rates = get_rates(category, tier, path, style)
    fees = apply_fees(cost_unit_price, category, tier, path, style)
    comprehensive = fees["comprehensive_unit_price"]

    subtotal = comprehensive * quantity  # 分部分项合计
    safety = subtotal * rates["safety_civil_rate"]  # 安全文明施工费（不可竞争）
    organization = subtotal * rates["organization_fee_rate"]  # 其他组织措施
    measure_total = safety + organization
    before_tax = subtotal + measure_total
    tax = before_tax * rates["tax_rate"]  # 税金（增值税一般计税 9%）
    total = before_tax + tax

    return {
        "category": category,
        "tier": tier,
        "rates": rates,
        "分部分项合计": round(subtotal, 2),
        "安全文明施工费": round(safety, 2),
        "其他组织措施费": round(organization, 2),
        "措施费合计": round(measure_total, 2),
        "税前造价": round(before_tax, 2),
        "税金(9%)": round(tax, 2),
        "含税总造价": round(total, 2),
    }
