"""特征描述驱动定价：将项目特征描述映射到定额子目，动态计算人材机成本。"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz, process

from src.knowledge.quota_manager import QuotaManager
from src.normalize.text import normalize_name, normalize_feature, normalize_unit


class FeatureToQuotaMatcher:
    """项目特征到定额子目的NLP匹配器。"""

    _CRAFT_KEYWORDS = {
        "抹灰": ["抹灰", "水泥砂浆", "找平"],
        "乳胶漆": ["乳胶漆", "无机涂料", "涂料", "面漆", "底漆"],
        "地砖": ["地砖", "块料", "瓷砖", "铺贴"],
        "石材": ["石材", "大理石", "花岗岩", "干挂"],
        "龙骨": ["龙骨", "轻钢", "吊顶"],
        "防水": ["防水", "卷材", "JS防水"],
        "门窗": ["门", "窗", "安装"],
        "油漆": ["油漆", "面漆", "底漆"],
        "天棚": ["天棚", "吊顶", "顶棚"],
        "墙面": ["墙面", "墙柱面"],
        "楼地面": ["楼地面", "地面", "楼面"],
        "扶手": ["扶手", "栏杆"],
        "结晶": ["结晶", "晶面", "抛光"],
    }

    _UNIT_MAP = {
        "㎡": ["平方米", "平方", "m2", "m²"],
        "m": ["米", "延长米", "m"],
        "100㎡": ["100平方米", "百平方米"],
        "100m": ["100米", "百米"],
    }

    def __init__(self, quota_mgr: Optional[QuotaManager] = None):
        self.quota_mgr = quota_mgr or QuotaManager()
        self._quota_index = None

    def _build_index(self):
        """构建定额索引（用于快速搜索）。"""
        if self._quota_index is None:
            conn = self.quota_mgr.repo.conn()
            try:
                rows = conn.execute(
                    "SELECT id, quota_code, name, unit, craft_category, work_content "
                    "FROM quota_standards"
                ).fetchall()
                self._quota_index = [dict(r) for r in rows]
            finally:
                conn.close()

    def match_by_feature(
        self,
        name: str,
        feature: str,
        unit: str,
        top_n: int = 3,
    ) -> List[Dict]:
        """根据项目特征描述匹配定额子目。"""
        self._build_index()
        
        text = normalize_name(f"{name}\n{feature}").lower()
        norm_unit = normalize_unit(unit).lower()

        scores = []
        for quota in self._quota_index:
            quota_text = f"{quota['name']} {quota.get('work_content', '')}".lower()
            
            name_score = fuzz.token_set_ratio(text, quota_text)
            feature_score = self._score_feature_match(text, quota)
            unit_score = self._score_unit_match(norm_unit, quota["unit"])
            
            total_score = 0.4 * name_score + 0.4 * feature_score + 0.2 * unit_score
            scores.append((quota, total_score))

        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for quota, score in scores[:top_n]:
            if score >= 40:
                results.append({
                    **quota,
                    "match_score": round(score, 2),
                    "match_reason": self._explain_match(text, quota),
                })
        return results

    def _score_feature_match(self, text: str, quota: Dict) -> float:
        """计算特征匹配得分。"""
        score = 0
        matches = 0
        
        work_content = quota.get("work_content", "").lower()
        craft_category = quota.get("craft_category", "").lower()
        
        for keyword, synonyms in self._CRAFT_KEYWORDS.items():
            if any(syn in text for syn in synonyms):
                if keyword in work_content or keyword in craft_category:
                    score += 25
                    matches += 1
                elif any(syn in work_content for syn in synonyms):
                    score += 15
                    matches += 1
        
        text_parts = re.split(r"[。；;\n]", text)
        for part in text_parts[:6]:
            if part.strip():
                part_score = fuzz.partial_ratio(part, work_content)
                if part_score > 60:
                    score += min(part_score, 15)
        
        return min(score, 100)

    def _score_unit_match(self, query_unit: str, quota_unit: str) -> float:
        """计算单位匹配得分。"""
        if not query_unit:
            return 50
        
        for std_unit, aliases in self._UNIT_MAP.items():
            if query_unit in aliases or std_unit.lower() in query_unit.lower():
                if quota_unit == std_unit:
                    return 100
                elif std_unit in quota_unit or quota_unit in std_unit:
                    return 80
        
        return 30

    def _explain_match(self, text: str, quota: Dict) -> str:
        """解释匹配原因。"""
        reasons = []
        
        work_content = quota.get("work_content", "")
        for keyword, synonyms in self._CRAFT_KEYWORDS.items():
            if any(syn in text for syn in synonyms):
                if keyword in work_content:
                    reasons.append(f"工艺关键词「{keyword}」匹配")
        
        if reasons:
            return "；".join(reasons)
        return "名称相似度匹配"

    def calculate_from_feature(
        self,
        name: str,
        feature: str,
        unit: str,
        labor_price: Optional[float] = None,
        mach_price: Optional[float] = None,
        material_prices: Optional[Dict[str, float]] = None,
        city: str = "",
        trade: str = "",
    ) -> Optional[Tuple[Dict, Dict]]:
        """根据特征描述计算人材机成本。

        labor_price/mach_price 为 None 时，按 city/trade 从 config/labor_rates.json
        自动读取（量价分离 + 城市分档）。
        """
        matches = self.match_by_feature(name, feature, unit, top_n=1)
        if not matches:
            return None
        
        best_match = matches[0]
        quota_code = best_match["quota_code"]
        
        cost = self.quota_mgr.calculate_cost(
            quota_code,
            material_price_dict=material_prices or {},
            labor_unit_price=labor_price,
            machinery_unit_price=mach_price,
            target_unit=unit,
            city=city,
            trade=trade,
        )
        
        if cost:
            return cost, best_match
        return None

    def parse_craft_steps(self, feature: str) -> List[str]:
        """解析项目特征中的施工工序步骤。"""
        steps = re.split(r"[。；;\n]", feature)
        steps = [s.strip() for s in steps if s.strip() and len(s.strip()) > 2]
        
        numbered_steps = []
        for step in steps:
            m = re.match(r"^\s*(\d+)[.．、]\s*(.+)", step)
            if m:
                numbered_steps.append(m.group(2).strip())
            else:
                numbered_steps.append(step)
        
        return numbered_steps