#!/usr/bin/env python3
"""AI联网询价模块 - 作为最终兜底定价机制"""
import json
import os
import time
import hashlib
from typing import Dict, Optional, Any
from dataclasses import dataclass

@dataclass
class AIInquiryResult:
    """AI询价结果"""
    name: str
    feature: str
    unit: str
    material_main: float
    material_aux: float
    labor: float
    machinery: float
    confidence: float
    source: str
    query_time: float
    expires_at: float

class AIPriceInquirer:
    """AI询价器 - 调用大语言模型或网络搜索获取材料价格"""
    
    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data', 'ai_inquiry_cache'
        )
        os.makedirs(self.cache_dir, exist_ok=True)
        self._cache: Dict[str, AIInquiryResult] = {}
    
    def _build_query_cache_key(self, name: str, feature: str, unit: str) -> str:
        """生成查询缓存键"""
        key_str = f"{name}||{feature}||{unit}"
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()
    
    def _load_cache(self) -> None:
        """加载缓存"""
        try:
            cache_path = os.path.join(self.cache_dir, 'inquiry_cache.json')
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, item in data.items():
                        self._cache[key] = AIInquiryResult(**item)
        except Exception:
            self._cache = {}
    
    def _save_cache(self) -> None:
        """保存缓存"""
        cache_path = os.path.join(self.cache_dir, 'inquiry_cache.json')
        data = {}
        for key, result in self._cache.items():
            # 只保存未过期的缓存
            if result.expires_at > time.time():
                data[key] = {
                    'name': result.name,
                    'feature': result.feature,
                    'unit': result.unit,
                    'material_main': result.material_main,
                    'material_aux': result.material_aux,
                    'labor': result.labor,
                    'machinery': result.machinery,
                    'confidence': result.confidence,
                    'source': result.source,
                    'query_time': result.query_time,
                    'expires_at': result.expires_at
                }
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _estimate_price_by_rules(self, name: str, feature: str, unit: str) -> AIInquiryResult:
        """基于规则估算价格（无网络时的兜底）"""
        full_text = f"{name} {feature}".lower()
        now = time.time()
        
        # 电气类
        if any(k in full_text for k in ['电缆', '电线', '导线', 'bv线', 'byj']):
            return AIInquiryResult(
                name=name, feature=feature, unit=unit,
                material_main=25, material_aux=2, labor=8, machinery=0.5,
                confidence=0.4, source='rule_based:electrical',
                query_time=now, expires_at=now + 86400 * 30
            )
        
        # 给排水类
        if any(k in full_text for k in ['管道', '阀门', '水表', '水管', '法兰']):
            return AIInquiryResult(
                name=name, feature=feature, unit=unit,
                material_main=50, material_aux=10, labor=25, machinery=5,
                confidence=0.4, source='rule_based:plumbing',
                query_time=now, expires_at=now + 86400 * 30
            )
        
        # 消防类
        if any(k in full_text for k in ['消防', '喷淋', '消火栓', '烟感', '报警']):
            return AIInquiryResult(
                name=name, feature=feature, unit=unit,
                material_main=80, material_aux=15, labor=35, machinery=3,
                confidence=0.4, source='rule_based:fire',
                query_time=now, expires_at=now + 86400 * 30
            )
        
        # 装饰类
        if any(k in full_text for k in ['石材', '瓷砖', '玻璃', '铝板', '木纹', '墙纸']):
            return AIInquiryResult(
                name=name, feature=feature, unit=unit,
                material_main=120, material_aux=20, labor=40, machinery=5,
                confidence=0.35, source='rule_based:decorative',
                query_time=now, expires_at=now + 86400 * 30
            )
        
        # 灯具类
        if any(k in full_text for k in ['灯', '照明', '筒灯', '射灯', '灯带']):
            return AIInquiryResult(
                name=name, feature=feature, unit=unit,
                material_main=100, material_aux=10, labor=15, machinery=0,
                confidence=0.4, source='rule_based:lighting',
                query_time=now, expires_at=now + 86400 * 30
            )
        
        # 空调通风类
        if any(k in full_text for k in ['空调', '风机', '风口', '风管', '盘管']):
            return AIInquiryResult(
                name=name, feature=feature, unit=unit,
                material_main=200, material_aux=30, labor=50, machinery=10,
                confidence=0.4, source='rule_based:hvac',
                query_time=now, expires_at=now + 86400 * 30
            )
        
        # 土建类
        if any(k in full_text for k in ['混凝土', '砂浆', '土方', '基础', '圈梁']):
            return AIInquiryResult(
                name=name, feature=feature, unit=unit,
                material_main=80, material_aux=20, labor=30, machinery=15,
                confidence=0.35, source='rule_based:civil',
                query_time=now, expires_at=now + 86400 * 30
            )
        
        # 默认估算
        return AIInquiryResult(
            name=name, feature=feature, unit=unit,
            material_main=50, material_aux=10, labor=20, machinery=2,
            confidence=0.25, source='rule_based:default',
            query_time=now, expires_at=now + 86400 * 30
        )
    
    def _query_llm(self, name: str, feature: str, unit: str, city: str = '') -> Optional[AIInquiryResult]:
        """调用大语言模型询价（预留接口）"""
        # 这里可以接入实际的LLM API，如OpenAI、阿里云、百度等
        # 目前返回None，使用规则估算兜底
        return None
    
    def inquire(
        self,
        name: str,
        feature: str = '',
        unit: str = '',
        city: str = '',
        use_cache: bool = True,
        cache_expire_hours: int = 72
    ) -> AIInquiryResult:
        """查询材料价格
        
        Args:
            name: 项目名称
            feature: 项目特征描述
            unit: 单位
            city: 城市
            use_cache: 是否使用缓存
            cache_expire_hours: 缓存过期时间（小时）
        
        Returns:
            AI询价结果
        """
        # 加载缓存
        self._load_cache()
        
        # 检查缓存
        cache_key = self._build_query_cache_key(name, feature, unit)
        if use_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            if cached.expires_at > time.time():
                return cached
        
        # 调用LLM询价（预留）
        llm_result = self._query_llm(name, feature, unit, city)
        if llm_result:
            self._cache[cache_key] = llm_result
            self._save_cache()
            return llm_result
        
        # 使用规则估算兜底
        result = self._estimate_price_by_rules(name, feature, unit)
        result.expires_at = time.time() + cache_expire_hours * 3600
        
        # 更新缓存
        self._cache[cache_key] = result
        self._save_cache()
        
        return result


# 全局实例
_inquirer: Optional[AIPriceInquirer] = None

def get_inquirer() -> AIPriceInquirer:
    """获取询价器单例"""
    global _inquirer
    if _inquirer is None:
        _inquirer = AIPriceInquirer()
    return _inquirer

def ai_inquire_price(
    name: str,
    feature: str = '',
    unit: str = '',
    city: str = ''
) -> Optional[Dict[str, Any]]:
    """便捷函数：调用AI询价"""
    inquirer = get_inquirer()
    result = inquirer.inquire(name, feature, unit, city)
    
    return {
        'material_main': result.material_main,
        'material_aux': result.material_aux,
        'labor': result.labor,
        'machinery': result.machinery,
        'confidence': result.confidence,
        'source': result.source,
    }
