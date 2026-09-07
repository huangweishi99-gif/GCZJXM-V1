# -*- coding: utf-8 -*-
"""dump 江门金标准完整行：编号/编码/名称/特征/采购方式/单位/工程量/人工/辅材机械/主材单价/损耗/主材费/综合费/综合单价"""
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
import openpyxl

GOLD = r'd:\projects\cost-estimation\清单数据资料\AI学习清单\江门新会骏凯豪庭五期三标项目1栋05户型精装修工程-投标报价-20260818.xlsx'
wb = openpyxl.load_workbook(GOLD, data_only=True, read_only=True)
ws = wb['标准层户型85']
out = io.open(r'd:\projects\cost-estimation\data\tmp\_tmp_jm_dump_full_out.txt', 'w', encoding='utf-8')
for i, row in enumerate(ws.iter_rows(values_only=True), 1):
    vals = ['' if v is None else str(v).replace('\n', '|') for v in row[:15]]
    # A编号 B编码 C名称 D特征 E索引 F采购 G单位 H工程量 I人工 J辅材机械 K主材单价 L损耗率 M主材费 N综合费 O综合单价
    if vals[2].strip() and vals[8]:
        out.write(f'L{i}\t{vals[0]}\t{vals[1]}\t{vals[2][:28]}\t{vals[3][:50]}\t{vals[4][:12]}\t{vals[5][:8]}\t{vals[6]}\t{vals[7]}\tI={vals[8]}\tJ={vals[9]}\tK={vals[10]}\tL={vals[11]}\tM={vals[12]}\tN={vals[13]}\tO={vals[14]}\n')
wb.close()
out.close()
print('done')
