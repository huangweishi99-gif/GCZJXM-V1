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
        self._price_mapper = None

    def _get_price_mapper(self):
        """惰性构建 定额材料名→信息价 映射器（缓存复用）。"""
        if self._price_mapper is None:
            from src.knowledge.material_price_mapper import MaterialPriceMapper

            self._price_mapper = MaterialPriceMapper(self.quota_mgr.load_price_info())
        return self._price_mapper

    def _mapped_material_prices(self, quota_code: str) -> Dict[str, float]:
        """对该定额子目的全部材料名映射信息价（未命中的不填充，走基期价兜底）。

        偏离守卫：OCR 错列行的基期价已失真（如湿拌砂浆M20 基期价53136元/m³），
        期刊价与失真基期价相差>10倍说明该行价量至少一端错位，放弃映射避免放大失真。
        """
        quota = self.quota_mgr.get_quota_by_code(quota_code)
        if not quota:
            return {}
        import json as _json

        mats = _json.loads(quota.get("material_json") or "{}")
        if not mats:
            return {}
        mapped, _ = self._get_price_mapper().build_price_dict(mats.keys())
        safe = {}
        for nm, price in mapped.items():
            md = mats.get(nm) or []
            base = float(md[2]) if len(md) >= 3 and isinstance(md[2], (int, float)) else 0.0
            if base > 0 and (price / base > 10 or base / price > 10):
                continue
            safe[nm] = price
        return safe

    def _build_index(self):
        """构建定额索引（用于快速搜索）。

        2026-10-19 装饰定额 OCR 子目名称大面积缺失（70% 页无章节名，子目名未提取），
        纯名称模糊匹配得分趋零。把材料消耗行名称并入索引文本——材料清单天然反映
        子目工作内容（块料子目含石材饰面板/地砖/砂浆），匹配得以进行。
        """
        if self._quota_index is None:
            import json as _json

            conn = self.quota_mgr.repo.conn()
            try:
                rows = conn.execute(
                    "SELECT id, quota_code, name, unit, craft_category, work_content, material_json "
                    "FROM quota_standards"
                ).fetchall()
                self._quota_index = []
                for r in rows:
                    d = dict(r)
                    try:
                        mats = _json.loads(d.pop("material_json") or "{}")
                        d["material_names"] = " ".join(mats.keys())
                    except (ValueError, TypeError):
                        d["material_names"] = ""
                    self._quota_index.append(d)
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
            quota_text = (f"{quota['name']} {quota.get('work_content') or ''} "
                          f"{quota.get('material_names', '')}").lower()
            
            name_score = fuzz.token_set_ratio(text, quota_text)
            feature_score = self._score_feature_match(text, quota)
            unit_score = self._score_unit_match(norm_unit, quota["unit"])
            
            total_score = 0.4 * name_score + 0.4 * feature_score + 0.2 * unit_score
            scores.append((quota, total_score))

        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for quota, score in scores[:top_n]:
            # 中文短名+扩大单位定额 token_set 天然低分；40 会让真实候选整批落空（2026-10-19 实证 32~38 分区间聚集）
            if score >= 35:
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
        
        # 子目名称/工作内容缺失时（装饰定额 OCR 实况），用名称+材料名承载工艺语义
        quota_text = (f"{quota.get('name') or ''} {quota.get('work_content') or ''} "
                      f"{quota.get('craft_category') or ''} "
                      f"{quota.get('material_names') or ''}").lower()

        for keyword, synonyms in self._CRAFT_KEYWORDS.items():
            if any(syn in text for syn in synonyms):
                if keyword in quota_text:
                    score += 25
                    matches += 1
                elif any(syn in quota_text for syn in synonyms):
                    score += 15
                    matches += 1

        text_parts = re.split(r"[。；;\n]", text)
        for part in text_parts[:6]:
            if part.strip():
                part_score = fuzz.partial_ratio(part, quota_text)
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
        
        quota_text = (f"{quota.get('name') or ''} {quota.get('work_content') or ''} "
                      f"{quota.get('material_names') or ''}")
        for keyword, synonyms in self._CRAFT_KEYWORDS.items():
            if any(syn in text for syn in synonyms):
                if keyword in quota_text:
                    reasons.append(f"工艺关键词「{keyword}」匹配")
        
        if reasons:
            return "；".join(reasons)
        return "名称相似度匹配"

    # craft_id → (册编码段, 材料名必含词之一): 工艺分类直查定额册。
    # 2026-10-20 实证：token_set 全文模糊对中文清单行不可用（400 定稿样本 388 个
    # <35 分）——圈定册段+材料词后候选集缩至数十，模糊分才恢复区分度。
    _CRAFT_ROUTE = {
        "electrical_cable": ("0302", ("电缆",)),
        "electrical_conduit": ("0302", ("电线管", "钢管", "塑料管", "配管")),
        "electrical_wiring": ("0302", ("绝缘电线", "导线", "电线")),
        "socket_outlet": ("0302", ("插座", "开关")),
        "cable_tray": ("0302", ("桥架",)),
        "electrical_light": ("0302", ("灯",)),
        "led_linear_light": ("0302", ("灯带", "灯槽", "线条灯", "灯")),
        # 2026-10-21 新入库册路由：消防→0307（水灭火：镀锌钢管/喷头/消火栓/沟槽件），
        # 暖通→0309（风管制作安装 030902 / 设备 030901）。
        # 圈词取材料名或子目名含其一——部分子目名是裸编码（OCR 名称列缺失，
        # 如 030701-10），语义靠材料名承载（实证材料名含镀锌钢管/薄钢板）。
        "fire": ("0307", ("镀锌钢管", "喷头", "消火栓", "沟槽", "无缝钢管")),
        "hvac_duct": ("0309", ("风管", "薄钢板", "酚醛", "玻镁")),
        "hvac_equipment": ("0309", ("空调器", "风机盘管", "机组", "风机", "换气扇")),
        # hvac_fcu（风机盘管）是既有独立 craft（component_judge 有专门价型），
        # 定额路由与 equipment 共用——match_by_craft 无路由时返回[]回落全文模糊易错册。
        "hvac_fcu": ("0309", ("风机盘管", "盘管")),
    }

    # 新册弱路由：圈候选=强信号但 token_set 中文短名无判别力（400 定稿样本实证
    # 388 个 <35 分），且风管尺寸档/设备型号/喷头型号不可规格化（风管子目名只有
    # 材质工艺无尺寸档；030701 整章子目名 OCR 缺失是裸编码）——复用 finish 路由
    # 的 60 分"仅建议"策略（<75 入价闸，不入价只推荐，人工确认后可用）。
    _WEAK_CRAFT = frozenset({"fire", "hvac_duct", "hvac_equipment", "hvac_fcu"})

    # 风管材质词：清单名含材质词时候选排序优先（不进分值，仅排序）
    _DUCT_MAT_WORDS = ("镀锌薄钢板", "镀锌钢板", "薄钢板", "不锈钢", "铝板",
                       "塑料", "复合", "酚醛", "玻镁", "玻璃钢", "聚氨酯")
    # 风管排除词：清单名未含该词时，子目名含该词降权（实证"镀锌薄钢板风管"被
    # "净化风管"子目抢位、"酚醛复合风管"被"圆形"子目抢位）
    _DUCT_EXCLUDE_WORDS = ("净化", "圆形", "圆管")

    # generic_finish 二级路由：craft 兜底类按名称/特征词二次细分。
    # 实证（400定稿样本）：该类混入大量电气件（电缆头/接线盒/地插）与装饰件，
    # 定额侧材料词已验证存在（终端27/接线盒6/插座12；龙骨77/涂料27/踢脚8；岩棉45）。
    _FINISH_ROUTE = [
        # 2026-10-21 市政高特异词必须排在通用"排水管"(0308) 之前——
        # "HDPE排水管DN300"是市政埋设语义，先命中防被室内排水(0308)抢走。
        # 材料词经 DB 实证圈定规模（聚乙烯20/混凝土管69/预应力7）。
        ("HDPE", "0404", ("聚乙烯", "高密度聚乙烯")),
        ("钢筋混凝土管", "0404", ("混凝土管", "钢筋混凝土管")),
        ("预应力混凝土管", "0404", ("预应力", "混凝土管")),
        ("金属软管", "0302", ("金属软管",)),
        ("镀锌钢管", "0308", ("镀锌钢管",)),
        ("PPR", "0308", ("PPR", "聚丙烯", "塑料给水管")),
        ("PVC", "0308", ("PVC", "聚氯乙烯")),
        ("给水管", "0308", ("给水管",)),
        ("排水管", "0308", ("排水管",)),
        ("电缆头", "0302", ("终端",)),
        ("接线盒", "0302", ("接线盒",)),
        ("地插", "0302", ("插座",)),
        ("吊顶", "0200", ("龙骨",)),
        ("龙骨", "0200", ("龙骨",)),
        ("保温", "0311", ("岩棉",)),
        ("踢脚", "0200", ("踢脚",)),
        ("乳胶漆", "0200", ("乳胶漆",)),
        ("涂料", "0200", ("涂料",)),
        ("墙纸", "0200", ("墙纸", "壁纸")),
        ("自流平", "0200", ("自流平",)),
        # 2026-10-21 市政/园林册路由（3595+580 子目，全部 60 分建议级——
        # 不入自动价只推荐人工确认，同暖通/消防闭环口径）。材料词经 DB
        # 实证圈定规模（沥青混凝土27/缘石4/路灯20/电缆沟2/标线7/乔木18）。
        # 已验证无覆盖不路由：井盖(276太大无区分度)/人行道/护栏/土方开挖
        # (材料名无词)——等真实市政清单样本再补。
        ("燃气管", "0406", ("燃气管", "聚乙烯")),
        ("沥青混凝土", "0401", ("沥青混凝土",)),
        ("乳化沥青", "0401", ("乳化沥青", "沥青")),
        ("缘石", "0401", ("缘石", "侧石")),
        ("侧石", "0401", ("缘石", "侧石")),
        ("电缆沟", "0407", ("电缆沟", "盖板")),
        ("路灯", "0407", ("路灯", "灯杆")),
        ("交通标志", "0408", ("标志牌", "标志杆")),
        ("标线", "0408", ("标线",)),
        ("乔木", "0500", ("乔木", "苗木")),
        ("灌木", "0500", ("灌木",)),
        ("草皮", "0500", ("草皮", "草坪")),
        ("苗木", "0500", ("苗木", "乔木")),
    ]

    def _finish_route(self, name: str, feature: str):
        """generic_finish 二级路由：名称+特征词命中即返回 (册段, 材料词)。"""
        text = (name or "") + (feature or "")
        for kw, seg, kws in self._FINISH_ROUTE:
            if kw in text:
                return (seg, kws)
        return None

    # 电缆规格模式：「3*50+2*25」「5x16」「5×50」→ 总芯数+主截面
    _CABLE_GROUPS = re.compile(r"(\d+)\s*[x×*]\s*(\d+)(?:\s*\+\s*(\d+)\s*[x×*]\s*(\d+))?")

    @classmethod
    def _parse_cable(cls, text: str):
        """从文本解析电缆 (总芯数, 主截面)。3*50+2*25→(5,50)，5×16→(5,16)。
        只取首个规格组：名称里规格唯一；跨组聚合会被粘连文本放大（实证 254mm²）。"""
        t = (text or "").replace(" ", "")
        m = cls._CABLE_GROUPS.search(t)
        if not m:
            return None
        n1, s1 = int(m.group(1)), int(m.group(2))
        if n1 > 100 or s1 > 1000:  # 页脚码/价格串误捕防御
            return None
        if m.group(3):
            n2, s2 = int(m.group(3)), int(m.group(4))
            if n2 > 100 or s2 > 1000:
                return None
            return (n1 + n2, max(s1, s2))
        return (n1, s1)

    # DN 规格：清单「配管PCDN20」→ 20。定额侧 OCR 粘连「DN205=2.75」(DN20 δ=2.75)，
    # 抓 [0-9]{2,3} 后按标准档表回退前两位；DN巧 等 OCR 错字依赖同子目多 mention 补集。
    _DN_STD = (15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150, 200, 250, 300, 350, 400)
    _DN_RAW = re.compile(r"dn\s*([0-9]{2,3})", re.I)  # 定额侧小写 dn 实况（接头零件dn32）
    _DN_QUERY = re.compile(r"DN\s*(\d+(?:\.\d+)?)", re.I)

    @classmethod
    def _dn_norm(cls, v: int):
        """抓取值→标准档：原位命中优先，否则截前两位（205→20 粘连回退）。"""
        if v in cls._DN_STD:
            return v
        v2 = v // 10
        return v2 if v2 in cls._DN_STD else None

    # 特征指纹工艺词：多候选时清单特征含某词且唯一候选子目名含该词→消歧成功。
    # 只信唯一匹配（≥2 候选含该词说明词不判别）。实证：清单特征"连接:螺纹" +
    # DN50 → 子目名"（螺纹连接）"唯一命中；电缆敷设章子目名全缺无法用。
    _TIE_BREAK_WORDS = ("螺纹", "热熔", "承插", "粘接", "焊接", "沟槽", "法兰",
                        "桥架", "直埋", "沿沟", "穿管", "暗配", "明配",
                        "干包", "热缩", "冷缩", "卡箍")

    def _feature_tiebreak(self, text_all: str, hits: List[Dict]):
        """返回 (消歧候选, 命中词) 或 (None, None)。"""
        blobbed = [(q, (q.get("name") or "") + (q.get("work_content") or ""))
                   for q in hits]
        for w in self._TIE_BREAK_WORDS:
            if w in text_all:
                matched = [q for q, blob in blobbed if w in blob]
                if len(matched) == 1:
                    return matched[0], w
        return None, None

    def _dn_spec_select(self, name: str, cands: List[Dict], mat_kws=(), feature: str = ""):
        """管材候选 DN 规格选优。两级：
        ①主材级（95分）：材料名含「圈定词+DN值」精确串——粘连碎片"钢管DN324"≠"钢管DN50"，
          天然免疫；②集合级（80分）：材料 DN 档集合相交，多命中按章集中度≥0.8 取最大章，
          低于则退回建议（防异章碎片撕裂，如配管PCDN32 碎片5:5打平）。"""
        m = self._DN_QUERY.search((name or "").replace(" ", ""))
        if not m:
            return []
        qdn = float(m.group(1))
        text_all = (name or "") + (feature or "")
        # ① 主材级精确串
        mats_hits = []
        for q in cands:
            mats = q.get("material_names") or ""
            for kw in mat_kws:
                if re.search(re.escape(kw) + r"\s*DN\s*0*" + re.escape(f"{qdn:g}"), mats, re.I):
                    mats_hits.append(q)
                    break
        if len(mats_hits) == 1:
            return [{**mats_hits[0], "match_score": 95.0,
                     "match_reason": f"DN{qdn:g}主材级精确匹配"}]
        if mats_hits:
            tb, w = self._feature_tiebreak(text_all, mats_hits)
            if tb is not None:
                return [{**tb, "match_score": 95.0,
                         "match_reason": f"DN{qdn:g}主材级特征指纹消歧[{w}]"}]
            return [{**mats_hits[0], "match_score": 80.0,
                     "match_reason": f"DN{qdn:g} 主材级多候选{len(mats_hits)}未消歧(连接方式)"}]
        # ② 集合级
        hits = []
        for q in cands:
            dns = set()
            for raw in self._DN_RAW.findall(q.get("material_names") or ""):
                dn = self._dn_norm(int(raw))
                if dn:
                    dns.add(dn)
            if qdn in dns:
                hits.append(q)
        if len(hits) == 1:
            return [{**hits[0], "match_score": 95.0,
                     "match_reason": f"DN{qdn:g}规格精确匹配"}]
        if hits:
            # 多命中按章(编码前6位)集中度取最大章内首条——防其他章材料的
            # DN 碎片（如配电装置"钢管DN324"粘连）把真正配管章挤出首位
            # （实证配管PCDN32碎片5:5打平误指030202）。
            # 集中度<0.8 说明命中被碎片撕裂，不给80分，退回建议级（60分）——
            # 80分≥75入价闸，异章子目入价风险不可接受。指纹词唯一命中可豁免。
            from collections import Counter
            chap = Counter(str(q.get("quota_code") or "")[:6] for q in hits)
            best, best_n = chap.most_common(1)[0]
            if best_n / len(hits) < 0.8:
                tb, w = self._feature_tiebreak(text_all, hits)
                if tb is not None:
                    return [{**tb, "match_score": 95.0,
                             "match_reason": f"DN{qdn:g}特征指纹消歧[{w}]"}]
                return []
            tb, w = self._feature_tiebreak(text_all, hits)
            if tb is not None:
                return [{**tb, "match_score": 95.0,
                         "match_reason": f"DN{qdn:g}特征指纹消歧[{w}]"}]
            first = next(q for q in hits
                         if str(q.get("quota_code") or "").startswith(best))
            return [{**first, "match_score": 80.0,
                     "match_reason": f"DN{qdn:g} 多候选{len(hits)}未消歧(章{best}集中)"}]
        return []

    # 电缆头截面：清单「(10mm2以下)」→ 10；定额材料「铜接线端子DT-16」「热缩型终端头25～50mm」
    _LUG_MM = re.compile(r"(\d+)\s*mm2?", re.I)
    _DT_LUG = re.compile(r"DT\s*[-一]?\s*(\d+)")
    _LUG_RANGE = re.compile(r"(\d+)\s*[~～]\s*(\d+)\s*mm")

    def _lug_spec_select(self, name: str, feature: str, cands: List[Dict]):
        """电缆头候选的截面档选优：清单截面落在定额端子档区间 [lo,hi] 即命中。
        排除中间头/矿物绝缘/户外章（清单为普通户内终端头）；相邻档边界重叠时
        取区间最窄档。唯一命中 95 分，多做法（干包/热缩）未消歧 80 分。"""
        m = self._LUG_MM.search((name or "").replace(" ", ""))
        if not m:
            return []
        sec = int(m.group(1))
        if sec > 500:  # 页脚码防御
            return []
        text_all = (name or "") + (feature or "")
        hits = []
        for q in cands:
            mats = q.get("material_names") or ""
            qname = q.get("name") or ""
            blob = mats + qname
            if "中间头" in blob or "矿物绝缘" in blob:
                continue
            if "户外" in qname and "户外" not in text_all:
                continue
            if "终端" not in blob:
                continue
            nums = [int(x) for x in self._DT_LUG.findall(mats)]
            for lo, hi in self._LUG_RANGE.findall(mats):
                nums.extend([int(lo), int(hi)])
            nums = [n for n in nums if n <= 630]  # DT300~500 档上限防御
            if not nums:
                continue
            lo, hi = min(nums), max(nums)
            if lo <= sec <= hi:
                hits.append((q, hi - lo))
        if not hits:
            return []
        hits.sort(key=lambda x: x[1])  # 边界重叠取区间最窄档
        if len(hits) == 1:
            return [{**hits[0][0], "match_score": 95.0,
                     "match_reason": f"电缆头截面{sec}mm²档[{hits[0][0].get('quota_code')}]唯一命中"}]
        # 干包/热缩/冷缩并列时，特征指纹词（如"类型:热缩"）唯一命中可消歧提 95
        tb, w = self._feature_tiebreak((name or "") + (feature or ""),
                                       [q for q, _ in hits])
        if tb is not None:
            return [{**tb, "match_score": 95.0,
                     "match_reason": f"电缆头截面{sec}mm²特征指纹消歧[{w}]"}]
        return [{**hits[0][0], "match_score": 80.0,
                 "match_reason": f"电缆头截面{sec}mm² 多档{len(hits)}未消歧(干包/热缩)"}]

    def _cable_spec_select(self, text: str, cands: List[Dict]):
        """电缆候选的规格结构化选优：总芯数+主截面双相等→命中。
        唯一命中 95 分；多命中（同规格多敷设方式，子目名 OCR 残缺无法二次消歧）
        取首 80 分并标注候选数。预分支电缆与普通电缆分流。"""
        qspec = self._parse_cable(text)
        if not qspec:
            return []
        is_prefab = "预分支" in text
        hits = []
        for q in cands:
            mats = q.get("material_names") or ""
            if ("预分支" in mats) != is_prefab:
                continue
            m = re.search(r"电力电缆[^ ]*?(\d+)\s*[x×]\s*(\d+)", mats)
            if not m:
                continue
            cores, sec = int(m.group(1)), int(m.group(2))
            if (cores, sec) == qspec:
                hits.append(q)
        if len(hits) == 1:
            return [{**hits[0], "match_score": 95.0,
                     "match_reason": f"电缆规格{qspec[0]}芯×{qspec[1]}精确匹配"}]
        if hits:
            return [{**hits[0], "match_score": 80.0,
                     "match_reason": f"电缆规格{qspec[0]}芯×{qspec[1]} 多候选{len(hits)}未消歧"}]
        return []

    def match_by_craft(
        self,
        name: str,
        feature: str,
        unit: str,
        top_n: int = 1,
    ) -> List[Dict]:
        """工艺分类直查路由：craft→册段+材料词圈候选，规格结构化选优优先，
        无规格解析时退回候选集内名称相似度。"""
        try:
            from src.normalize.craft_classifier import classify_craft

            cm = classify_craft(name or "", feature or "", unit or "")
        except Exception:
            return []
        cid = getattr(cm, "craft_id", None)
        is_finish_route = False
        if cid == "generic_finish":
            # 兜底类二次细分：电缆头/接线盒/吊顶/保温等按词表直查对应册
            route = self._finish_route(name, feature)
            if route:
                cid = f"finish:{route[0]}:{route[1][0]}"
                is_finish_route = True
        else:
            route = self._CRAFT_ROUTE.get(cid or "")
        if cid == "electrical_cable" and "电缆沟" in (name or ""):
            # craft 子串误抢修正："电缆沟/电缆井"含"电缆"被 electrical_cable
            # 抢走，0302 段圈不到候选变无路由——让位市政 0407（60 分建议级）。
            route = ("0407", ("电缆沟", "盖板"))
            is_finish_route = True
        if not route:
            return []
        seg, mat_kws = route
        self._build_index()
        # 圈候选：材料名**或子目名**含关键词（实证 030208-114 干包终端头材料只有
        # 「铜接线端子DT-n」，「终端」在子目名——只看材料名会把干包章整章圈漏）
        cands = [
            q for q in self._quota_index
            if str(q.get("quota_code") or "").startswith(seg)
            and any(k in ((q.get("material_names") or "") + (q.get("name") or ""))
                    for k in mat_kws)
        ]
        if not cands:
            return []
        text = normalize_name(f"{name}\n{feature}").lower()

        # 规格结构化选优（电缆已实证：token_set 对规格串无判别力，全给22-25分）。
        # 规格只从名称解析——feature 经 normalize 后与名称粘连会重复捕获规格组。
        spec_hits = []
        if cid == "electrical_cable":
            spec_hits = self._cable_spec_select(normalize_name(name or "").lower(), cands)
        elif cid == "finish:0302:终端":
            spec_hits = self._lug_spec_select(name or "", feature or "", cands)
        elif cid == "electrical_conduit" or cid.startswith("finish:0308:") \
                or cid == "finish:0302:金属软管":
            dn_kws = mat_kws
            if cid == "electrical_conduit" and re.search(
                    r"PC|PVC|塑料|硬塑", name or "", re.I):
                # 塑料配管分流：主材级只搜塑料管词——防钢管构件 DN 粘连碎片
                # （实证"钢管DN324"=DN32 δ4 粘连，把配管PCDN32拖去配电装置章）
                dn_kws = ("塑料管", "电线管", "硬聚氯乙烯", "PVC")
            spec_hits = self._dn_spec_select(name or "", cands, dn_kws, feature or "")
        elif cid == "fire" and self._DN_RAW.search(name or ""):
            # 消防管 DN 选优：复用给排水册验证过的主材级精确串+章集中度防线
            # （沟槽/法兰/丝扣连接词走 _dn_spec_select 内部特征指纹消歧）。
            # 无 DN 的消防行（喷头/消火栓/装置）不规格化，落弱兜底建议。
            spec_hits = self._dn_spec_select(
                name or "", cands, ("镀锌钢管", "无缝钢管", "沟槽"), feature or "")
        if spec_hits:
            return spec_hits[:top_n]

        scored = []
        for q in cands:
            qtext = (f"{q['name']} {q.get('work_content') or ''} "
                     f"{q.get('material_names', '')}").lower()
            s_tok = fuzz.token_set_ratio(text, qtext)
            # partial_ratio 对中文短名友好（最大公共子串比例）：实证"喷淋头" vs
            # "水灭火系统喷头安装" token_set<15 落空，partial≈66% 正常。
            s_part = fuzz.partial_ratio(text, qtext)
            scored.append((q, s_tok, s_part))
        # 风管材质词排序优先：同圈候选里材质匹配排前（不进分值仅排序，防
        # "酚醛复合风管"被镀锌薄钢板子目挤掉）；清单未说"净化/圆形"时相应子目降权
        if cid == "hvac_duct":
            mats = [w for w in self._DUCT_MAT_WORDS if w in text]
            excs = [w for w in self._DUCT_EXCLUDE_WORDS if w not in text]
            scored.sort(key=lambda x: (
                any(w in x[0]['name'] for w in mats),
                not any(w in x[0]['name'] for w in excs),
                x[2]), reverse=True)
        elif cid in self._WEAK_CRAFT:
            scored.sort(key=lambda x: x[2], reverse=True)
        else:
            scored.sort(key=lambda x: x[1], reverse=True)
        out = []
        for q, s_tok, s_part in scored[:top_n]:
            s = s_tok  # 门槛判分统一用 token_set（防跑偏），partial 仅参与排序
            # 弱路由（generic_finish 二次细分 + 新册 fire/hvac 系）：圈内 token_set
            # 无判别力（实证电缆头类 22-26 分/400 样本 388 个 <35 分），候选圈定
            # 本身是强信号但无规格选优背书——圈内 top1 固定 60 分"仅建议"
            # （低于 75 入价闸，不入自动价只推荐人工确认）。
            if is_finish_route or cid in self._WEAK_CRAFT:
                # 门槛双轨：token>=15 或 partial>=25（实证"喷淋头" vs "水灭火系统
                # 喷头安装" token_set<15 被误杀；partial≈66% 正常——候选圈定
                # 册段+材料词已是强约束，门槛仅二次防跑偏）。
                # 2026-10-21 finish 路由同享双轨：市政行"HDPE双壁波纹排水管
                # DN300"规格串拉低 token_set(<15)，partial 45-53% 正常被误杀
                # （400 定稿样本实证 token_set 对中文短串 388/400 个 <35）。
                if s >= 15 or ((cid in self._WEAK_CRAFT or is_finish_route)
                               and s_part >= 25):
                    tag = "新册弱路由" if cid in self._WEAK_CRAFT and not is_finish_route else "craft路由"
                    out.append({
                        **q,
                        "match_score": 60.0,
                        "match_reason": f"{tag}[{cid}] 候选{len(cands)} 弱匹配仅建议(token{s:.0f}/part{s_part:.0f}%)",
                    })
            elif s >= 50:
                out.append({
                    **q,
                    "match_score": round(s, 2),
                    "match_reason": f"craft路由[{cid}] 候选{len(cands)} 相似{s:.0f}%",
                })
        return out

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
        matches = self.match_by_craft(name, feature, unit, top_n=1)
        if not matches:
            matches = self.match_by_feature(name, feature, unit, top_n=1)
        if not matches:
            return None

        best_match = matches[0]
        quota_code = best_match["quota_code"]

        # 量价分离：调用方未显式给价字典时，用 材料名→信息价映射器 填充
        # （命中如湿拌砂浆M10→357/m³；未命中保持基期价兜底）
        price_dict = dict(material_prices or {})
        if not price_dict:
            price_dict = self._mapped_material_prices(quota_code)

        cost = self.quota_mgr.calculate_cost(
            quota_code,
            material_price_dict=price_dict,
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