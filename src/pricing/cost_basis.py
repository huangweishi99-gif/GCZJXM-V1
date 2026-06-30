# -*- coding: utf-8 -*-
"""成本区合价口径：净价(÷1.1) vs 毛价(=价库合价)。"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

from src.normalize.text import normalize_name, normalize_unit


@lru_cache(maxsize=1)
def _load_rules() -> dict:
    p = Path(__file__).resolve().parents[2] / "config" / "cost_basis_rules.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {
        "default_net_divisor": 1.1,
        "gross_name_patterns": [r"MT-0\d.*金属饰面"],
        "gross_unit_name_rules": [{"unit": "m", "name_pattern": r"AM-0\d"}],
    }


def get_net_divisor(price_cfg: dict | None = None) -> float:
    rules = _load_rules()
    d = float((price_cfg or {}).get("cost_net_divisor") or rules.get("default_net_divisor") or 1.1)
    return d if d > 1.0 else 1.0


def _compiled_patterns(raw: List[str]) -> Tuple[re.Pattern, ...]:
    out: List[re.Pattern] = []
    for pat in raw:
        try:
            out.append(re.compile(pat, re.I))
        except re.error:
            continue
    return tuple(out)


def prefer_net_price(name: str, feature: str = "", unit: str = "") -> bool:
    """
    默认按净价（÷net_divisor）；gross 规则见 config/cost_basis_rules.json。
    """
    rules = _load_rules()
    name_n = normalize_name(name)
    u = normalize_unit(unit)

    for pat in _compiled_patterns(rules.get("gross_name_patterns") or []):
        if pat.search(name_n):
            return False

    for rule in rules.get("gross_unit_name_rules") or []:
        ru = normalize_unit(rule.get("unit") or "")
        if ru and u != ru:
            continue
        np = rule.get("name_pattern") or ""
        if np and re.search(np, name_n, re.I):
            return False

    return True
