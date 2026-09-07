"""广联达定额管理：定额子目导入、匹配和消耗量计算。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.knowledge.repository import KnowledgeRepository


class QuotaManager:
    """定额标准管理类。"""

    def __init__(self, repo: Optional[KnowledgeRepository] = None):
        self.repo = repo or KnowledgeRepository()

    def ensure_quota_table(self) -> None:
        """确保quota_standards表存在（旧版 schema 自动重建迁移）。"""
        conn = self.repo.conn()
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(quota_standards)").fetchall()}
            if cols and "labor_consumption" not in cols:
                # 旧版 schema：labor/material_main/material_aux/machinery 等列
                conn.execute("DROP TABLE IF EXISTS quota_standards")
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS quota_standards (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        quota_code TEXT UNIQUE NOT NULL,
                        name TEXT NOT NULL,
                        unit TEXT NOT NULL,
                        labor_consumption REAL DEFAULT 0,
                        material_json TEXT DEFAULT '{}',
                        machinery_json TEXT DEFAULT '{}',
                        craft_category TEXT,
                        work_content TEXT,
                        chapter TEXT,
                        section TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )"""
                )
                conn.commit()
                return
            conn.execute(
                """CREATE TABLE IF NOT EXISTS quota_standards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quota_code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    labor_consumption REAL DEFAULT 0,
                    material_json TEXT DEFAULT '{}',
                    machinery_json TEXT DEFAULT '{}',
                    craft_category TEXT,
                    work_content TEXT,
                    chapter TEXT,
                    section TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_quota_code ON quota_standards(quota_code)"""
            )
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_quota_name ON quota_standards(name)"""
            )
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_quota_category ON quota_standards(craft_category)"""
            )
            conn.commit()
        finally:
            conn.close()

    def insert_quota_item(
        self,
        quota_code: str,
        name: str,
        unit: str,
        labor_consumption: float = 0,
        materials: Optional[Dict[str, Tuple[float, str]]] = None,
        machinery: Optional[Dict[str, Tuple[float, str]]] = None,
        craft_category: Optional[str] = None,
        work_content: Optional[str] = None,
        chapter: Optional[str] = None,
        section: Optional[str] = None,
    ) -> int:
        """插入一条定额子目。"""
        conn = self.repo.conn()
        try:
            materials = materials or {}
            machinery = machinery or {}
            cur = conn.execute(
                """INSERT OR REPLACE INTO quota_standards
                    (quota_code, name, unit, labor_consumption, material_json,
                     machinery_json, craft_category, work_content, chapter, section)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    quota_code,
                    name,
                    unit,
                    labor_consumption,
                    json.dumps(materials, ensure_ascii=False),
                    json.dumps(machinery, ensure_ascii=False),
                    craft_category,
                    work_content,
                    chapter,
                    section,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def search_quota(self, name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """按名称模糊搜索定额子目。"""
        conn = self.repo.conn()
        try:
            rows = conn.execute(
                """SELECT * FROM quota_standards
                    WHERE name LIKE ? OR quota_code LIKE ?
                    ORDER BY LENGTH(name) ASC
                    LIMIT ?""",
                (f"%{name}%", f"%{name}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_quota_by_code(self, quota_code: str) -> Optional[Dict[str, Any]]:
        """按定额编号查询。"""
        conn = self.repo.conn()
        try:
            row = conn.execute(
                """SELECT * FROM quota_standards WHERE quota_code=?""",
                (quota_code,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def calculate_cost(
        self,
        quota_code: str,
        material_price_dict: Optional[Dict[str, float]] = None,
        labor_unit_price: Optional[float] = None,
        machinery_unit_price: Optional[float] = None,
        target_unit: str = "",
        city: str = "",
        trade: str = "",
    ) -> Optional[Dict[str, float]]:
        """根据定额消耗量计算人材机成本。

        Args:
            quota_code: 定额编号
            material_price_dict: 材料价格字典
            labor_unit_price: 人工单价（元/工日），None 时按 city/trade 从 labor_rates.json 取
            machinery_unit_price: 机械单价（元/台班），None 时按 city 从 labor_rates.json 取
            target_unit: 目标清单单位（用于单位换算）
            city: 城市（用于人工/机械单价分档）
            trade: 工种（用于人工单价分档）

        Returns:
            人材机成本字典，单位为目标清单单位
        """
        quota = self.get_quota_by_code(quota_code)
        if not quota:
            return None

        if labor_unit_price is None or machinery_unit_price is None:
            rates = self._labor_rates(city, trade)
            labor_unit_price = labor_unit_price or rates["labor_unit_price"]
            machinery_unit_price = machinery_unit_price or rates["machinery_unit_price"]

        material_price_dict = material_price_dict or {}
        materials = json.loads(quota.get("material_json") or "{}")
        machinery = json.loads(quota.get("machinery_json") or "{}")
        quota_unit = quota.get("unit", "")

        labor_cost = float(quota["labor_consumption"]) * labor_unit_price

        material_cost = 0.0
        for mat_name, mat_data in materials.items():
            if len(mat_data) >= 2:
                consumption, consumption_unit = mat_data[:2]
            else:
                continue
            # 量价分离：优先用外部市场价/信息价，其次定额内嵌价，最后估算兜底
            price = material_price_dict.get(mat_name, 0)
            if price <= 0 and len(mat_data) >= 4:
                price = mat_data[2]
            if price <= 0:
                price = self._estimate_material_price(mat_name)
            material_cost += consumption * price

        machinery_cost = 0.0
        for mach_name, mach_data in machinery.items():
            if len(mach_data) >= 4:
                consumption, consumption_unit, price, price_unit = mach_data
            elif len(mach_data) >= 2:
                consumption, _ = mach_data[:2]
                price = machinery_unit_price
            else:
                continue
            machinery_cost += consumption * price

        conversion_factor = self._calculate_conversion_factor(quota_unit, target_unit)

        return {
            "labor": round(labor_cost / conversion_factor, 2),
            "material_main": round(material_cost / conversion_factor, 2),
            "material_aux": 0,
            "machinery": round(machinery_cost / conversion_factor, 2),
        }

    def _calculate_conversion_factor(self, quota_unit: str, target_unit: str) -> float:
        """计算定额单位到清单单位的换算系数。
        
        定额单位通常为扩大单位（如100㎡、100m），需要换算到清单单位（如㎡、m）。
        
        Example:
            quota_unit="100㎡", target_unit="㎡" → factor=100
            quota_unit="100m", target_unit="m" → factor=100
            quota_unit="㎡", target_unit="㎡" → factor=1
            quota_unit="100㎡", target_unit="100㎡" → factor=1
        """
        import re
        
        quota_unit = quota_unit.strip()
        target_unit = target_unit.strip().lower()
        
        if not target_unit:
            return 1.0
        
        if quota_unit.lower() == target_unit:
            return 1.0
        
        m = re.match(r"(\d+)\s*(.+)", quota_unit)
        if m:
            multiplier = int(m.group(1))
            base_unit = m.group(2).strip()
            
            base_unit_norm = base_unit.lower().replace("m2", "㎡")
            target_unit_norm = target_unit.replace("m2", "㎡")
            
            if base_unit_norm == target_unit_norm or target_unit_norm in base_unit_norm:
                return float(multiplier)
        
        return 1.0

    def _estimate_material_price(self, material_name: str) -> float:
        """估算材料价格（兜底）。价格单位与定额消耗量单位匹配。

        价格口径与 config/quota_standards.json、深圳信息价保持一致（2026 市场价）。
        """
        price_map = {
            "水泥": 500,
            "中砂": 120,
            "细砂": 130,
            "水": 5,
            "腻子": 1.5,
            "腻子粉": 1.5,
            "乳胶漆": 18,
            "底漆": 15,
            "面漆": 18,
            "地砖": 80,
            "面砖": 60,
            "石材": 150,
            "大理石": 180,
            "花岗岩": 200,
            "石膏板": 25,
            "轻钢龙骨": 8,
            "龙骨": 8,
            "不锈钢龙骨": 25,
            "铝合金": 200,
            "铝扣板": 80,
            "干挂件": 5,
            "膨胀螺栓": 1.5,
            "云石胶": 15,
            "白水泥": 500,
            "勾缝剂": 8,
            "密封胶": 20,
            "防水涂料": 25,
            "防水卷材": 30,
            "结晶粉": 20,
            "抛光剂": 25,
            "钢丝棉": 2,
            "焊接材料": 10,
            "合页": 30,
            "门锁": 100,
            "螺丝": 0.1,
            "木门": 300,
            "铝合金窗": 200,
            "金属扶手": 150,
            "弯头": 30,
            "水泥砂浆": 200,
            "砂浆": 150,
        }
        for key, price in price_map.items():
            if key in material_name:
                return price
        return 0

    def _labor_rates(self, city: str = "", trade: str = "") -> Dict[str, float]:
        """按 城市×工种 读取人工/机械单价（元/工日、元/台班）。

        fallback 链：city>trade > city>default > default。
        """
        path = Path(__file__).parent.parent.parent / "config" / "labor_rates.json"
        default = {
            "labor_unit_price": 320,
            "machinery_unit_price": 120,
        }
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cfg = data.get("cities", {})
            city_cfg = cfg.get(city or "", {}) if city else {}
            # city 级默认
            labor = city_cfg.get("labor_unit_price") or data.get("default", {}).get("labor_unit_price") or default["labor_unit_price"]
            mach = city_cfg.get("machinery_unit_price") or data.get("default", {}).get("machinery_unit_price") or default["machinery_unit_price"]
            # 工种细分覆盖
            trades = city_cfg.get("trades") or data.get("default", {}).get("trades") or {}
            if trade and trade in trades:
                labor = trades[trade]
            return {"labor_unit_price": float(labor), "machinery_unit_price": float(mach)}
        except Exception:
            return dict(default)

    def stats(self) -> Dict[str, int]:
        """统计定额数据。"""
        conn = self.repo.conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM quota_standards").fetchone()[0]
            categories = conn.execute(
                "SELECT craft_category, COUNT(*) FROM quota_standards GROUP BY craft_category"
            ).fetchall()
            return {
                "total_items": total,
                "categories": {cat: cnt for cat, cnt in categories},
            }
        finally:
            conn.close()

    def import_from_json(self, json_path: str) -> int:
        """从JSON文件导入定额数据。"""
        self.ensure_quota_table()
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        imported = 0
        for item in data.get("quota_items", []):
            self.insert_quota_item(
                quota_code=item["quota_code"],
                name=item["name"],
                unit=item["unit"],
                labor_consumption=item.get("labor_consumption", 0),
                materials=item.get("materials", {}),
                machinery=item.get("machinery", {}),
                craft_category=item.get("craft_category"),
                work_content=item.get("work_content"),
                chapter=item.get("chapter"),
                section=item.get("section"),
            )
            imported += 1
        return imported

    def load_price_info(self, json_path: str = None) -> Dict[str, float]:
        """加载深圳造价信息作为材料价格字典。
        
        Args:
            json_path: 价格信息JSON文件路径，默认为config/shenzhen_price_info_2023.json
        
        Returns:
            材料名称到价格的字典
        """
        if json_path is None:
            json_path = str(Path(__file__).parent.parent.parent / "config" / "shenzhen_price_info_2023.json")
        
        price_dict: Dict[str, float] = {}
        try:
            data = json.loads(Path(json_path).read_text(encoding="utf-8"))
            for category, items in data.get("categories", {}).items():
                for key, item in items.items():
                    # 添加材料名称到价格映射
                    name = item.get("name", "")
                    if name:
                        price_dict[name] = item.get("price", 0)
                        # 添加规格名称到价格映射
                        spec = item.get("spec", "")
                        if spec:
                            price_dict[f"{name} {spec}"] = item.get("price", 0)
        except Exception:
            # 文件不存在时返回空字典
            pass
        
        return price_dict