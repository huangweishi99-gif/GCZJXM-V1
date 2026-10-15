#!/usr/bin/env python3
"""AI联网询价模块 - 作为最终兜底定价机制"""
import json
import os
import time
import hashlib
import urllib.request
import urllib.error
from typing import Dict, Optional, Any
from dataclasses import dataclass

try:
    from src.config.ai_model import load_ai_model_config
except Exception:  # 极简场景下允许 import 失败
    load_ai_model_config = None  # type: ignore

_SYSTEM_PROMPT = """你是中国工程造价询价助手。基于用户给定的【项目名称/项目特征/单位/城市】，
给出该清单项的【主材/辅材/人工/机械】单价（人民币元，保留 2 位小数）。

口径：
- 主材：该项的核心材料（如石材、瓷砖、电线、风机盘管）
- 辅材：施工耗材（胶、钉、接头、油漆等）
- 人工：人工费合计（按现浇装饰装修口径）
- 机械：机具摊销/台班（一般 0~5 元；大型设备可能 50~200）

严格只输出 JSON，不要任何解释或 markdown：
{"material_main": 数字, "material_aux": 数字, "labor": 数字, "machinery": 数字, "reason": "一句话依据"}"""

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
        """调用大语言模型（OpenAI 兼容 API）询价。失败返 None。"""
        if load_ai_model_config is None:
            return None
        cfg = load_ai_model_config()
        base_url = (cfg.get("base_url") or "").rstrip("/")
        api_key = cfg.get("api_key") or ""
        model = cfg.get("model_name") or "grok-4.7"
        if not base_url or not api_key:
            return None

        user_prompt = (
            f"项目名称：{name or '未知'}\n"
            f"项目特征：{feature or '无'}\n"
            f"单位：{unit or '无'}\n"
            f"城市：{city or '不限'}\n"
            f"请基于以上信息给出人材机单价。"
        )
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": int(cfg.get("max_tokens") or 400),
            "temperature": float(cfg.get("temperature") or 0.1),
        }

        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            timeout = int(cfg.get("timeout_seconds") or 60)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            content = content.strip()
            # 容忍 ```json 包裹
            if content.startswith("```"):
                content = content.strip("`")
                if "\n" in content:
                    content = content.split("\n", 1)[1]
            obj = json.loads(content)
            now = time.time()
            return AIInquiryResult(
                name=name,
                feature=feature,
                unit=unit,
                material_main=float(obj.get("material_main") or 0),
                material_aux=float(obj.get("material_aux") or 0),
                labor=float(obj.get("labor") or 0),
                machinery=float(obj.get("machinery") or 0),
                confidence=0.65,  # LLM 询价 conf 中等
                source=f"llm:{model}",
                query_time=now,
                expires_at=now + 86400 * 30,
            )
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, json.JSONDecodeError, TimeoutError) as exc:
            # 失败不抛异常，调用方会走规则估算兜底
            self._last_llm_error = f"{type(exc).__name__}: {exc}"
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
