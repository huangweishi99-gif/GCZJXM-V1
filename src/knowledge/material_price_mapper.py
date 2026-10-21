"""材料名 → 2026.09 信息价映射器。

两端都带 OCR/口径噪声：定额侧是消耗量风格名（铁件（综合）/湿拌抹灰砂浆M20/
墙面砖600mm×600mm），期刊侧是刊例键（砂浆 M20/钢管（内衬PE） DN300/大量苗木粘连）。

分层匹配（保守：规格不一致绝不匹配，未命中回退调用方兜底）：
  L1 规范化精确相等
  L2 键集合包含（期刊键以规范名开头，且键余下部分只是单位/括号）
  L3 核心名 + 规格双匹配（砂浆等级/砖规格/管径等显式规格必须相等）
  L4 无规格核心名唯一命中（期刊侧该核心词只有一个键且无规格差异）

用法：
    mapper = MaterialPriceMapper(qm.load_price_info())
    price, key, method = mapper.lookup("湿拌抹灰砂浆M20")
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Optional, Tuple

# ---- OCR/口径修复表（保守：只放确定映射） ----
_CHAR_FIX = {
    "χ": "x", "Χ": "X", "×": "x", "*": "x", "✕": "x",
    "．": ".", "·": ".", "•": ".",
    "（": "(", "）": ")",
    "φ": "φ", "Φ": "φ", "小": "φ", "寸": "φ",  # 定额OCR φ→小
    "一": "-", "–": "-", "—": "-",
}
# 括号说明词：定额「（综合）」「（成品）」等不影响价格匹配
_PAREN_NOISE = re.compile(r"\((综合|成品|一级|二级|三级|普通|标准|综合价|预算价)\)")
# 尾部计量单位词（不构成价格区分）
_UNIT_WORDS = re.compile(
    r"(?:\d+\s*(?:mL|ml|ML|升|L|g|kg|KG|千克|吨|t|T|支|片|套|个|只|根|条|块|桶|卷|袋|箱|m|米|㎡|m2|mm|cm))+$")
# 显式规格模式：匹配上则两侧规格必须一致
_SPEC_PATTERNS = {
    "mortar": re.compile(r"M\s*(\d+(?:\.\d+)?)"),          # 砂浆强度等级 M20
    "tile": re.compile(r"(\d{3,4})\s*(?:mm)?\s*[x×*]\s*(\d{3,4})"),  # 600x600 砖/板规格
    "dn": re.compile(r"DN\s*(\d+(?:\.\d+)?)", re.I),
    "dia": re.compile(r"φ\s*(\d+(?:\.\d+)?)"),
    "thick": re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm)?厚"),
}
# 砂浆档位 OCR 粘连修复：M103=M10粘"3"、M巧5.303=M20粘连（定额页脚码混入）。
# 档位>50 不可能是真实强度（装饰砂浆常见 M5~M30），截前两位。
_MORTAR_GARBLED = re.compile(r"M\s*(\d{3,})")
# 档位坏形 MI()=M10（I→1、()→0，2026-10-21 实证 230 行：湿拌砂浆MI()/螺栓MI()mm×20mm套）
_MI_GARBLED = re.compile(r"M\s*I\s*\(\s*\)")


def _normalize(raw: str) -> str:
    """双端共用规范化。"""
    s = unicodedata.normalize("NFKC", raw or "")
    for a, b in _CHAR_FIX.items():
        s = s.replace(a, b)
    s = _MI_GARBLED.sub("M10", s)  # 必须在剥括号/单位之前
    s = _PAREN_NOISE.sub("", s)
    s = re.sub(r"\s+", "", s)
    # 循环剥离尾部单位词（玻璃胶300mL支 → 玻璃胶300）
    for _ in range(4):
        s2 = re.sub(r"(?<=\d)(?:mL|ml|ML|升|L|支|片|套|个|只|根|条|块|桶|卷|袋|台班)$", "", s)
        if s2 == s:
            break
        s = s2
    return s


def _core_name(s: str) -> str:
    """去掉规格片段后的名称核心，用于 L3/L4。"""
    s = re.sub(r"M\s*\d+(?:\.\d+)?", "", s)
    s = re.sub(r"\d{3,4}\s*(?:mm)?\s*x\s*\d{3,4}", "", s)
    s = re.sub(r"DN\s*\d+(?:\.\d+)?", "", s, flags=re.I)
    s = re.sub(r"φ\s*\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)?", "", s)
    s = re.sub(r"\d+(?:\.\d+)?\s*(?:mm)?厚", "", s)
    s = re.sub(r"[x×*]\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)?$", "", s)  # 尾部截面 25x25x2.5
    s = re.sub(r"\d+(?:\.\d+)?$", "", s)  # 尾部孤立数字
    s = re.sub(r"(?:mm|m2|㎡|cm)$", "", s)  # 规格清掉后的单位碎片
    return s.strip("-._/() ")


def _specs(s: str) -> Dict[str, Tuple]:
    out: Dict[str, Tuple] = {}
    m = _SPEC_PATTERNS["mortar"].search(s)
    if m:
        grade = float(m.group(1))
        if grade > 50:  # OCR 粘连页脚码（M103→M10），真实砂浆档位不超 M50
            garbled = _MORTAR_GARBLED.search(s)
            if garbled:
                grade = float(garbled.group(1)[:2])
        out["mortar"] = (grade,)
    m = _SPEC_PATTERNS["tile"].search(s)
    if m:
        out["tile"] = (int(m.group(1)), int(m.group(2)))
    m = _SPEC_PATTERNS["dn"].search(s)
    if m:
        out["dn"] = (float(m.group(1)),)
    m = _SPEC_PATTERNS["dia"].search(s)
    if m:
        out["dia"] = (float(m.group(1)),)
    m = _SPEC_PATTERNS["thick"].search(s)
    if m:
        out["thick"] = (float(m.group(1)),)
    return out


class MaterialPriceMapper:
    """定额材料名 → 期刊价 查找器。"""

    def __init__(self, price_dict: Dict[str, float]):
        self.price_dict = price_dict
        # 规范化索引：norm_key -> (原键, 价)
        self._index: Dict[str, Tuple[str, float]] = {}
        # 核心名索引：core -> [(norm_key, 价, specs)]
        self._core_index: Dict[str, list] = {}
        for k, v in price_dict.items():
            nk = _normalize(k)
            if not nk or v <= 0:
                continue
            self._index[nk] = (k, v)
            core = _core_name(nk)
            if core:
                self._core_index.setdefault(core, []).append((nk, v, _specs(nk)))

    def lookup(self, quota_mat_name: str) -> Tuple[Optional[float], str, str]:
        """返回 (价格, 命中键, 方法)。未命中返回 (None, '', '')。"""
        qn = _normalize(quota_mat_name)
        if not qn:
            return None, "", ""
        # L1 精确
        hit = self._index.get(qn)
        if hit:
            return hit[1], hit[0], "exact"
        # L2 键前缀（期刊键以定额规范名开头，余下仅为单位/括号碎片）
        for nk, (ok, v) in self._index.items():
            if nk.startswith(qn):
                rest = nk[len(qn):]
                if not rest or re.fullmatch(r"[\d.]+|mm|m2|㎡|m|kg|t", rest):
                    return v, ok, "prefix"
        # L3/L4 核心名匹配：定额核心常以期刊核心为后缀（湿拌抹灰砂浆→砂浆），
        # 期刊核心必须≥2字且为定额核心后缀，防止「胶」这类单字误配。
        qcore = _core_name(qn)
        qspecs = _specs(qn)
        cands = []
        for kcore, entries in self._core_index.items():
            if len(kcore) >= 2 and qcore.endswith(kcore):
                cands.extend(entries)
        if qspecs and cands:
            for nk, v, kspecs in cands:
                if kspecs == qspecs:
                    return v, self._index[nk][0], "core+spec"
        elif cands:
            # L4 无规格唯一命中：期刊核心词过泛的品类禁止（玻璃/地毯等基础料价
            # 远低于加工品，无规格匹配会严重低估，如钢化夹胶玻璃→玻璃 25.56）
            generic_cores = {"玻璃", "地毯", "水泥", "砖", "钢材", "电缆", "电线"}
            blocked = any(qcore != gc and qcore.endswith(gc) for gc in generic_cores)
            safe = [] if blocked else cands
            spec_less = [(nk, v) for nk, v, ks in safe if not ks]
            if len(spec_less) == len(safe) and len(safe) == 1:
                return safe[0][1], self._index[safe[0][0]][0], "core"
        return None, "", ""

    def build_price_dict(self, quota_mat_names) -> Tuple[Dict[str, float], Dict[str, str]]:
        """批量映射。返回 (填充到 material_price_dict 的 {定额原名:价}, {定额原名:方法})。"""
        out: Dict[str, float] = {}
        methods: Dict[str, str] = {}
        for nm in quota_mat_names:
            price, key, method = self.lookup(nm)
            if price is not None:
                out[nm] = price
                methods[nm] = method
        return out, methods
