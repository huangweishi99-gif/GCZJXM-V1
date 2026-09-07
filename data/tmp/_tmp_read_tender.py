# -*- coding: utf-8 -*-
"""读取物资招标文件，提取项目地点/工期/供货要求。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tmp_docx_read as reader

SRC = r"D:\工作\投标项目\珠海海德公馆会所项目-20260618\招标文件\珠海丹田海德精装修工程招标（专业、劳务、物资）20260819\3、珠海丹田海德公馆项目 精装修材料-招标文件.docx"
OUT = r"d:\projects\cost-estimation\data\tmp\_tmp_tender_out.txt"

reader.DOCX = SRC
reader.OUT = OUT
import io
buf = io.StringIO()
_orig = sys.stdout
sys.stdout = buf
try:
    reader.main()
finally:
    sys.stdout = _orig
with open(OUT, "w", encoding="utf-8") as f:
    f.write(buf.getvalue())
print("DONE")
