# -*- coding: utf-8 -*-
"""无样本清单项的外部造价参考（网页搜索 + 本地 hints 缓存）。"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[2]
HINTS_PATH = ROOT / "config" / "external_price_hints.json"


@dataclass
class ExternalPriceHint:
    query: str
    name: str
    feature: str
    unit: str
    city: str
    search_url: str
    snippets: List[str]
    parsed_prices: List[float]
    note: str = ""
    date: str = ""


def _load_hints() -> dict:
    if HINTS_PATH.exists():
        return json.loads(HINTS_PATH.read_text(encoding="utf-8"))
    return {"_comment": "外部搜索缓存，供 market_reference 人工审核后并入", "hints": []}


def _save_hints(data: dict) -> None:
    HINTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    HINTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_search_query(name: str, feature: str = "", unit: str = "", city: str = "") -> str:
    parts = [city, name.split("\n")[0][:40]]
    if unit:
        parts.append(f"单位{unit}")
    feat = (feature or "").replace("\n", " ")[:60]
    if feat:
        parts.append(feat)
    parts.append("装修 造价 综合单价 2024 2025")
    return " ".join(p for p in parts if p)


def _fetch_ddg_snippets(query: str, *, timeout: int = 12) -> List[str]:
    """DuckDuckGo HTML 摘要（离线失败时返回空）。"""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; CostPricingBot/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return []
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</', html, re.I | re.S)
    clean = []
    for s in snippets[:5]:
        t = re.sub(r"<[^>]+>", "", s)
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            clean.append(t[:300])
    return clean


def _parse_prices_from_text(text: str) -> List[float]:
    found = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*元\s*/?\s*(?:㎡|m2|m²|米|m|樘|套)", text, re.I):
        v = float(m.group(1))
        if 0.5 < v < 50000:
            found.append(v)
    for m in re.finditer(r"综合单价[^\d]{0,20}(\d+(?:\.\d+)?)", text):
        v = float(m.group(1))
        if 0.5 < v < 50000:
            found.append(v)
    return sorted(set(found))[:5]


def search_external_price(
    name: str,
    feature: str = "",
    unit: str = "",
    *,
    city: str = "深圳",
    fetch_web: bool = True,
    save: bool = True,
) -> ExternalPriceHint:
    query = build_search_query(name, feature, unit, city)
    search_url = "https://www.baidu.com/s?wd=" + urllib.parse.quote(query)
    snippets: List[str] = []
    if fetch_web:
        snippets = _fetch_ddg_snippets(query)
    parsed: List[float] = []
    for sn in snippets:
        parsed.extend(_parse_prices_from_text(sn))
    parsed = sorted(set(parsed))[:5]
    hint = ExternalPriceHint(
        query=query,
        name=name,
        feature=(feature or "")[:200],
        unit=unit,
        city=city,
        search_url=search_url,
        snippets=snippets,
        parsed_prices=parsed,
        note="自动抓取摘要中的单价数字，需人工核实后写入 market_reference_prices.json",
        date=str(date.today()),
    )
    if save:
        data = _load_hints()
        hints = data.setdefault("hints", [])
        hints.append(asdict(hint))
        if len(hints) > 200:
            data["hints"] = hints[-200:]
        _save_hints(data)
    return hint
