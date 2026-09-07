# -*- coding: utf-8 -*-
"""engine.search 对真实招标行的匹配测试"""
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
from src.pricing.engine import PricingEngine
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.query import PricingContext

repo = KnowledgeRepository()
engine = PricingEngine()
ctx = PricingContext(city='江门', price_tier='mid')

out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_search_out.txt', 'w', encoding='utf-8')
cases = [
    ('楼地面', '1.材料品种：瓷砖（CT-01）冠珠800*800 GF-DIQT80329ZH 2.规格：长边规格800mm（含）以内综合考虑 3.铺贴形式：正铺、斜铺、错位铺、工字铺、田字形', 'm2'),
    ('内墙涂料', '1.基层处理：刮腻子2遍 2.涂料品种：内墙乳胶漆（PT-03）三棵树 3.涂刷遍数：一底两面', 'm2'),
    ('单联单控开关', '1.规格：单联单控 2.品牌：公牛G33 3.安装方式：暗装', '个'),
]
for name, feat, unit in cases:
    out.write(f'## {name}\n')
    cands = engine.search(name, feat, unit, top_n=5)
    for c in cands[:5]:
        out.write(f'  sid={c.get("standard_item_id")} "{c.get("name")}" name_score={c.get("name_score"):.2f} feat_score={c.get("feature_score"):.2f} tag={c.get("tag_score"):.2f} total={c.get("total_score",0):.2f} samples={c.get("sample_count")} 摘要={str(c.get("做法摘要"))[:30]}\n')
    if not cands:
        out.write('  (无候选)\n')
    out.write('\n')
out.close()
print('done')
