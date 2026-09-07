# -*- coding: utf-8 -*-
"""learn 江门金标准进知识库"""
import io, json, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
from src.knowledge.repository import KnowledgeRepository

fp = r'd:\projects\cost-estimation\清单数据资料\AI学习清单\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价-20260818.xlsx'
repo = KnowledgeRepository()
result = repo.learn_from_file(
    fp,
    project_name='江门新会骏凯豪庭五期三标1栋05户型',
    city='江门',
    price_tier='mid',
    export_anatomy=False,
)
out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_learn_out.txt', 'w', encoding='utf-8')
out.write(json.dumps(result, ensure_ascii=False, indent=2))
out.write('\n\n' + json.dumps(repo.stats(), ensure_ascii=False, indent=2))
out.close()
print('done')
