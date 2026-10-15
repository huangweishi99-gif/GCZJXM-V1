"""AI联网询价Agent：当无历史匹配和定额时，调用外部建材价格API实时询价。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.knowledge.repository import KnowledgeRepository


class PriceInquiryAgent:
    """建材价格询价智能体。"""

    def __init__(self, repo: Optional[KnowledgeRepository] = None):
        self.repo = repo or KnowledgeRepository()
        self.cache_path = Path(__file__).resolve().parents[3] / "data" / "price_cache.json"
        self._cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        """加载价格缓存。"""
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except:
                return {}
        return {}

    def _save_cache(self):
        """保存价格缓存。"""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _get_cached_price(
        self,
        name: str,
        feature: str,
        unit: str,
        city: str = "深圳",
        max_age_hours: int = 72,
    ) -> Optional[Dict]:
        """从缓存获取价格。"""
        key = f"{city}_{name}_{feature}_{unit}"
        entry = self._cache.get(key)
        if entry:
            age = (time.time() - entry["timestamp"]) / 3600
            if age <= max_age_hours:
                return entry["price"]
        return None

    def _cache_price(
        self,
        name: str,
        feature: str,
        unit: str,
        price: Dict,
        city: str = "深圳",
    ):
        """缓存价格。"""
        key = f"{city}_{name}_{feature}_{unit}"
        self._cache[key] = {
            "price": price,
            "timestamp": time.time(),
            "city": city,
        }
        self._save_cache()

    def inquire(
        self,
        name: str,
        feature: str,
        unit: str,
        city: str = "深圳",
        tier: str = "mid",
    ) -> Optional[Dict[str, float]]:
        """询价主入口：先查缓存，再调用API。"""
        cached = self._get_cached_price(name, feature, unit, city)
        if cached:
            return cached

        price = self._call_price_api(name, feature, unit, city, tier)
        if price:
            self._cache_price(name, feature, unit, price, city)
            return price

        price = self._estimate_price(name, feature, unit)
        if price:
            self._cache_price(name, feature, unit, price, city)
            return price

        return None

    def _call_price_api(
        self,
        name: str,
        feature: str,
        unit: str,
        city: str,
        tier: str,
    ) -> Optional[Dict[str, float]]:
        """调用外部建材价格API。"""
        api_config = self._get_api_config()
        
        if not api_config.get("enabled"):
            return None

        try:
            url = api_config["endpoint"]
            params = {
                "keyword": name,
                "spec": feature,
                "unit": unit,
                "city": city,
                "tier": tier,
                "api_key": api_config["api_key"],
            }

            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return self._parse_api_response(data)
        except Exception as e:
            print(f"API调用失败: {e}")
        
        return None

    def _get_api_config(self) -> Dict[str, Any]:
        """获取API配置：从 config/ai_model.json + .env 读取。"""
        try:
            from src.config.ai_model import load_ai_model_config
            cfg = load_ai_model_config()
        except Exception:
            cfg = {}
        return {
            "enabled": bool(cfg.get("base_url") and cfg.get("api_key")),
            "endpoint": (cfg.get("base_url") or "").rstrip("/") + "/chat/completions",
            "api_key": cfg.get("api_key", ""),
            "model": cfg.get("model_name", "grok-4.7"),
            "timeout": int(cfg.get("timeout_seconds") or 60),
            "max_tokens": int(cfg.get("max_tokens") or 400),
        }

    def _parse_api_response(self, data: Dict) -> Optional[Dict[str, float]]:
        """解析API响应。"""
        result = data.get("result")
        if not result:
            return None

        return {
            "material_main": float(result.get("material_price") or 0),
            "material_aux": float(result.get("aux_price") or 0),
            "labor": float(result.get("labor_price") or 0),
            "machinery": float(result.get("machinery_price") or 0),
        }

    def _estimate_price(
        self,
        name: str,
        feature: str,
        unit: str,
    ) -> Optional[Dict[str, float]]:
        """基于规则估算价格（兜底）。"""
        text = f"{name} {feature}".lower()
        
        price_rules = [
            (["乳胶漆", "无机涂料", "涂料"], 85, 56, 110, 2),
            (["地砖", "瓷砖"], 82, 14, 48, 2),
            (["石材", "大理石"], 380, 120, 150, 8),
            (["防水", "卷材"], 50, 20, 30, 1),
            (["石膏板", "龙骨"], 25, 15, 30, 1),
            (["铝扣板", "天花"], 80, 20, 35, 2),
            (["木门", "门框"], 300, 50, 100, 5),
            (["铝合金", "窗户"], 200, 30, 80, 3),
            (["结晶", "晶面"], 15, 0.5, 40, 0.3),
            (["扶手", "栏杆"], 150, 30, 80, 5),
            (["电线", "电缆"], 10, 2, 5, 0.5),
            (["开关", "插座"], 50, 5, 30, 0),
            (["灯具", "照明"], 200, 20, 50, 5),
            (["洁具", "水龙头"], 500, 30, 100, 2),
            (["智能马桶"], 3000, 50, 200, 10),
            (["智能门锁", "指纹锁"], 800, 30, 150, 5),
            (["电动窗帘", "窗帘轨道"], 300, 20, 50, 2),
            (["充电桩", "电动汽车充电"], 2000, 100, 500, 20),
            (["新风系统", "新风"], 5000, 200, 800, 50),
            (["中央空调", "空调"], 8000, 300, 1000, 100),
            (["地暖", "地热"], 200, 50, 80, 5),
            (["浴霸", "取暖"], 500, 20, 100, 5),
            (["淋浴花洒", "花洒"], 850, 30, 100, 2),
            (["恒温阀"], 47, 12, 30, 0),
            (["灭火器", "消防"], 150, 10, 30, 0),
            (["风机", "排风"], 500, 50, 100, 20),
        ]

        for keywords, main, aux, labor, mach in price_rules:
            if any(kw in text for kw in keywords):
                return {
                    "material_main": main,
                    "material_aux": aux,
                    "labor": labor,
                    "machinery": mach,
                }

        return None

    def batch_inquire(
        self,
        items: List[Dict[str, str]],
        city: str = "深圳",
        tier: str = "mid",
    ) -> List[Optional[Dict[str, float]]]:
        """批量询价。"""
        results = []
        for item in items:
            price = self.inquire(
                item["name"],
                item.get("feature", ""),
                item["unit"],
                city=city,
                tier=tier,
            )
            results.append(price)
        return results

    def clear_cache(self):
        """清空价格缓存。"""
        self._cache = {}
        self._save_cache()

    def cache_stats(self) -> Dict[str, int]:
        """缓存统计。"""
        return {
            "cached_items": len(self._cache),
        }