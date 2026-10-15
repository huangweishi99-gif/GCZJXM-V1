# -*- coding: utf-8 -*-
"""定稿报价口径：综合单价 = 成本单价 × 综合系数。

系数来自 config/quote_styles.json，按项目在 config/project_pairs.json 的
quote_style 字段登记。未登记的项目走 cost_equals_quote（系数 1.0），
与「投标方需求一般表头」管利税全 0 的默认约定一致。

损耗档只在组价结果损耗率为空、且名称能对上定稿习惯时补一档，
不覆盖各专项价型已经给出的损耗率。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent.parent
STYLES_PATH = ROOT / "config" / "quote_styles.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    if not STYLES_PATH.exists():
        return {}
    try:
        return json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def style_of(style_id: str) -> dict:
    """取一个口径的完整定义；未知 id 回落到默认口径。"""
    cfg = _load()
    styles = cfg.get("styles") or {}
    key = style_id or cfg.get("default_style") or "cost_equals_quote"
    found = styles.get(key) or styles.get(cfg.get("default_style") or "") or {}
    return {
        "id": key if key in styles else (cfg.get("default_style") or "cost_equals_quote"),
        "label": str(found.get("label") or "成本即报价"),
        "markup": float(found.get("markup") or 1.0),
        "tax_rate": float(found.get("tax_rate") or 0.0),
        "note": str(found.get("note") or ""),
    }


def markup_of(style_id: str) -> float:
    """综合系数。1.0 表示综合单价等于成本单价。"""
    return style_of(style_id)["markup"]


def resolve_style(pair: Optional[dict]) -> str:
    """从项目登记解析口径 id。

    显式 quote_style 优先；其次兼容旧的 price_style 字段；都没有则默认。
    """
    if not pair:
        return style_of("")["id"]
    explicit = str(pair.get("quote_style") or pair.get("price_style") or "").strip()
    if explicit and explicit in (_load().get("styles") or {}):
        return explicit
    return style_of("")["id"]


def suggest_loss_rate(name: str, feature: str = "") -> Optional[float]:
    """按定稿习惯给损耗率档位。

    只看名称（特征里的做法描述会把辅料带偏），命中即返回；
    没有任何关键词命中时返回 None，调用方应保持原值不动。
    """
    text = name or ""
    rules = (_load().get("loss_rates") or {}).get("by_keyword") or []
    for rule in rules:
        if any(k and k in text for k in rule.get("keywords") or []):
            return float(rule.get("rate") or 0.0)
    return None
