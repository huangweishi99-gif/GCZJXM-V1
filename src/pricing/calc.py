"""投标方表头公式链：成本 → 管理 → 利润 → 税金 → 综合单价。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PriceBreakdown:
    material_main: float = 0.0
    material_loss_rate: float = 0.0
    labor: float = 0.0
    material_aux: float = 0.0
    machinery: float = 0.0
    cost_unit_price: float = 0.0
    management: float = 0.0
    profit: float = 0.0
    tax: float = 0.0
    unit_price: float = 0.0

    def with_quantity(self, qty: float) -> tuple[float, float]:
        cost_amount = round(self.cost_unit_price * qty, 2)
        amount = round(self.unit_price * qty, 2)
        return cost_amount, amount


def calc_cost_unit_price(
    material_main: float,
    material_loss_rate: float,
    labor: float,
    material_aux: float,
    machinery: float,
) -> float:
    return material_main * (1 + material_loss_rate) + labor + material_aux + machinery


def calc_from_components(
    material_main: float = 0.0,
    material_loss_rate: float = 0.0,
    labor: float = 0.0,
    material_aux: float = 0.0,
    machinery: float = 0.0,
    *,
    management_rate: float = 0.035,
    profit_rate: float = 0.05,
    tax_rate: float = 0.09,
) -> PriceBreakdown:
    """与对比表 Excel 公式一致。"""
    cost = calc_cost_unit_price(
        material_main, material_loss_rate, labor, material_aux, machinery
    )
    mgmt = cost * management_rate
    prof = (cost + mgmt) * profit_rate
    tax = (cost + mgmt + prof) * tax_rate
    unit = cost + mgmt + prof + tax
    return PriceBreakdown(
        material_main=material_main,
        material_loss_rate=material_loss_rate,
        labor=labor,
        material_aux=material_aux,
        machinery=machinery,
        cost_unit_price=round(cost, 4),
        management=round(mgmt, 4),
        profit=round(prof, 4),
        tax=round(tax, 4),
        unit_price=round(unit, 4),
    )
