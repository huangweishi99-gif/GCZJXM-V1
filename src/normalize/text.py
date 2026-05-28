"""项目名称、特征、单位规范化。"""
from __future__ import annotations

import re
import unicodedata

_UNIT_MAP = {
    "m2": "㎡",
    "m²": "㎡",
    "M2": "㎡",
    "平方米": "㎡",
    "平米": "㎡",
    "平方": "㎡",
    "m3": "m³",
    "立方米": "m³",
    "立方": "m³",
    "米": "m",
    "M": "m",
    "个": "个",
    "项": "项",
    "套": "套",
    "组": "组",
    "台": "台",
    "樘": "樘",
    "扇": "扇",
}

_SYNONYMS = [
    ("砼", "混凝土"),
    ("砼", "混凝土"),
    ("\r\n", "\n"),
    ("\r", "\n"),
]


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def normalize_unit(unit: str | None) -> str:
    if unit is None:
        return ""
    u = _nfkc(str(unit)).strip()
    u = u.replace("计量\n单位", "").replace("计量单位", "")
    u = re.sub(r"\s+", "", u)
    return _UNIT_MAP.get(u, u)


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    s = _nfkc(str(name)).strip()
    for a, b in _SYNONYMS:
        s = s.replace(a, b)
    s = re.sub(r"\s+", "", s)
    return s


def normalize_feature(feature: str | None) -> str:
    if feature is None:
        return ""
    s = _nfkc(str(feature)).strip()
    for a, b in _SYNONYMS:
        s = s.replace(a, b)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    lines = []
    for line in s.split("\n"):
        line = line.strip()
        line = re.sub(r"^(\d+)[.、．]\s*", r"\1.", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def feature_fingerprint(feature_norm: str) -> str:
    """用于检索的紧凑指纹。"""
    s = feature_norm.replace("\n", "|")
    s = re.sub(r"\s+", "", s)
    return s[:500]


# 项目特征常见条目前缀（清单规范：1.部位 2.做法 … 每点一道工序）
_CRAFT_PREFIX = re.compile(
    r"^(\d+)[.、．)]\s*|^[（(]\d+[)）]\s*|^[-•·]\s*"
)


def parse_craft_points(feature: str | None) -> List[str]:
    """
    将项目特征拆成施工工艺条目（每行/每点一道工序）。
    造价组价时：名称定项，特征定工法与单价。
    """
    text = normalize_feature(feature)
    if not text:
        return []

    points: List[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if len(line) < 4:
            continue
        line = _CRAFT_PREFIX.sub("", line).strip()
        if not line:
            continue
        # 跳过纯栏目名
        if re.fullmatch(r"(部位|做法|工艺|材料|厚度|规格|项目特征|工作内容)[：:]?", line):
            continue
        points.append(line)

    # 单行内用分号罗列的多点做法
    if len(points) <= 1 and "；" in text:
        parts = [_CRAFT_PREFIX.sub("", p).strip() for p in text.split("；")]
        parts = [p for p in parts if len(p) >= 6]
        if len(parts) >= 2:
            points = parts

    return points
