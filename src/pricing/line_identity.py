# -*- coding: utf-8 -*-
"""
清单组价身份：每条清单须同时对照 **项目名称 + 项目特征 + 单位** 才能确定成本口径。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from src.normalize.text import normalize_name, normalize_unit


@dataclass(frozen=True)
class LineIdentity:
    name: str
    feature: str
    unit: str
    name_norm: str
    feature_norm: str
    unit_norm: str

    @property
    def has_unit(self) -> bool:
        return bool(self.unit_norm)

    @property
    def has_feature(self) -> bool:
        return bool(self.feature_norm)

    @property
    def feature_rich_enough(self) -> bool:
        """特征过短则无法可靠对照工序（仅名称+单位不够）。"""
        return len(self.feature_norm) >= 8


def parse_line_identity(
    name: str,
    feature: str = "",
    unit: str = "",
) -> LineIdentity:
    return LineIdentity(
        name=name or "",
        feature=feature or "",
        unit=unit or "",
        name_norm=normalize_name(name),
        feature_norm=normalize_name(feature),
        unit_norm=normalize_unit(unit),
    )


def feature_rich_enough(ident: LineIdentity, min_chars: int = 8) -> bool:
    return len(ident.feature_norm) >= min_chars


def units_must_match(unit_a: str, unit_b: str) -> bool:
    """历史/规则价须与清单单位一致（已规范化）。"""
    a, b = normalize_unit(unit_a), normalize_unit(unit_b)
    if not a or not b:
        return False
    return a == b


def check_pricing_identity(
    name: str,
    feature: str = "",
    unit: str = "",
    *,
    require_unit: bool = True,
    require_feature: bool = False,
    min_feature_chars: int = 8,
) -> Tuple[bool, str]:
    """
    返回 (可否组价, 原因)。
    require_feature=True 时无足够特征则拒绝任何自动组价。
    """
    ident = parse_line_identity(name, feature, unit)
    if require_unit and not ident.has_unit:
        return False, "缺少清单单位，无法确定单价口径"
    if require_feature and not feature_rich_enough(ident, min_feature_chars):
        return False, "项目特征缺失或过短，须对照特征工序才能组价"
    if not ident.name_norm:
        return False, "缺少项目名称"
    return True, ""


def auto_fill_requires_feature(
    ident: LineIdentity,
    *,
    min_feature_chars: int = 8,
) -> Tuple[bool, str]:
    """自动填价前：有单位且特征可对照。"""
    if not ident.has_unit:
        return False, "自动填价须明确清单单位"
    if not feature_rich_enough(ident, min_feature_chars):
        return False, "自动填价须对照项目特征（特征描述过短）"
    return True, ""


def pricing_basis_note(ident: LineIdentity) -> str:
    u = ident.unit_norm or "?"
    f_len = len(ident.feature_norm)
    return f"对照口径：名称+特征({f_len}字)+单位({u})"
