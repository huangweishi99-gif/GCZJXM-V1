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
    region: str = "",
) -> Dict[str, float]:
    """取综合单价费率建议。

    Args:
        category: 工程类别（装饰装修/土建/安装/幕墙/市政），未知走 default
        tier: 档位（high/mid/low）
        style: 项目风格（如 batch_fitout 批量精装 12%），优先级最高
        region: 地区口径（如 guangdong）。广东安文费与利润以「人工费+机械费」
            为基数，费率与基数键（safety_base/profit_base）一并返回

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

    # 地区口径最后叠加：广东安文费/利润改按「人工费+机械费」计取
    region_over = (cfg.get("regions") or {}).get(region or "")
    if region_over:
        rates["region"] = region
        for key in ("safety_base", "profit_base"):
            if region_over.get(key):
                rates[key] = region_over[key]
        safety = region_over.get("safety_rate") or {}
        if isinstance(safety, dict):
            rates["safety_civil_rate"] = float(
                safety.get(category or "") or safety.get("_default") or 0
            )
        if region_over.get("profit_rate") is not None:
            rates["profit_rate"] = float(region_over["profit_rate"])

    return rates


def apply_fees(
    cost_unit_price: float,
    category: str = "",
    tier: str = "mid",
    path: Optional[str] = None,
    style: str = "",
    region: str = "",
    labor: float = 0.0,
    machinery: float = 0.0,
) -> Dict[str, float]:
    """在成本单价基础上计取 管理费+利润+风险，得到综合单价。

    广东口径下利润以「人工费+机械费」为基数（labor/machinery 为 0 时
    退回按成本单价计取，并在返回中标注 profit_base_fallback）。

    Returns:
        {management_fee, profit, risk, comprehensive_unit_price}
    """
    rates = get_rates(category, tier, path, style, region)
    mgmt = cost_unit_price * rates["management_fee_rate"]
    risk = cost_unit_price * rates["risk_rate"]
    fallback = False
    if rates.get("profit_base") == "labor_machinery":
        base = labor + machinery
        if base > 0:
            profit = base * rates["profit_rate"]
        else:
            profit = cost_unit_price * rates["profit_rate"]
            fallback = True
    else:
        profit = cost_unit_price * rates["profit_rate"]
    out = {
        "management_fee": round(mgmt, 2),
        "profit": round(profit, 2),
        "risk": round(risk, 2),
        "comprehensive_unit_price": round(cost_unit_price + mgmt + profit + risk, 2),
        "rates": rates,
    }
    if fallback:
        out["profit_base_fallback"] = True
    return out


def build_summary(
    cost_unit_price: float,
    quantity: float,
    category: str = "",
    tier: str = "mid",
    path: Optional[str] = None,
    style: str = "",
    region: str = "",
    labor: float = 0.0,
    machinery: float = 0.0,
) -> Dict[str, Any]:
    """生成单位工程费用汇总（分部分项 → 措施 → 规费 → 税金 → 含税总价）。

    广东口径下安全文明施工费以「人工费+机械费」为基数（labor/machinery
    为 0 时退回按分部分项合计计取，并标注 safety_base_fallback）。
    """
    rates = get_rates(category, tier, path, style, region)
    fees = apply_fees(
        cost_unit_price, category, tier, path, style, region, labor, machinery
    )
    comprehensive = fees["comprehensive_unit_price"]

    subtotal = comprehensive * quantity  # 分部分项合计
    safety_fallback = False
    if rates.get("safety_base") == "labor_machinery":
        lm_total = (labor + machinery) * quantity
        if lm_total > 0:
            safety = lm_total * rates["safety_civil_rate"]
        else:
            safety = subtotal * rates["safety_civil_rate"]
            safety_fallback = True
    else:
        safety = subtotal * rates["safety_civil_rate"]  # 安全文明施工费（不可竞争）
    organization = subtotal * rates["organization_fee_rate"]  # 其他组织措施
    measure_total = safety + organization
    before_tax = subtotal + measure_total
    tax = before_tax * rates["tax_rate"]  # 税金（增值税一般计税 9%）
    total = before_tax + tax

    out: Dict[str, Any] = {
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
    if safety_fallback:
        out["safety_base_fallback"] = True
    if fees.get("profit_base_fallback"):
        out["profit_base_fallback"] = True
    return out
