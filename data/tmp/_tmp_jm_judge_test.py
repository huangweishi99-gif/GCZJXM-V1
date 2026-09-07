# -*- coding: utf-8 -*-
"""测试 judge 对江门行的判定来源"""
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
from src.knowledge.repository import KnowledgeRepository
from src.pricing.engine import PricingEngine
from src.knowledge.query import PricingContext
from src.pricing.component_judge import judge_line_components

repo = KnowledgeRepository()
engine = PricingEngine()
ctx = PricingContext(city='江门', price_tier='mid')

out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_judge_test_out.txt', 'w', encoding='utf-8')
cases = [
    ('楼地面', '1.材料品种：瓷砖（CT-01）冠珠800*800 2.铺贴方式：干铺 3.找平层：20厚1:3水泥砂浆 4.品牌：冠珠', 'm2'),
    ('内墙涂料', '1.基层处理：刮腻子2遍 2.涂料品种：内墙乳胶漆（PT-03）三棵树 3.涂刷遍数：一底两面', 'm2'),
    ('户内门 M1', '1.门类型：PVC木质门（含门套） 2.规格：M1 3.含五金', '樘'),
    ('单联单控开关', '1.规格：单联单控 2.品牌：公牛G33 3.安装方式：暗装', '个'),
    ('强化木地板', '1.材料品种：强化复合木地板 2.含防潮垫 3.铺装方式：悬浮铺装', 'm2'),
]
for name, feat, unit in cases:
    j = judge_line_components(name, feat, unit, engine, repo, ctx=ctx)
    out.write(f'## {name}\n')
    out.write(f'  source={j.source} confidence={j.confidence:.2f}\n')
    out.write(f'  主材={j.material_main} 损耗={j.material_loss_rate} 人工={j.labor} 辅材={j.material_aux} 机械={j.machinery}\n')
    out.write(f'  notes={j.notes[:3]}\n')
    out.write(f'  warnings={j.warnings[:2]}\n\n')
out.close()
print('done')
