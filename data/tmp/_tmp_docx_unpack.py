# -*- coding: utf-8 -*-
"""调用 skill unpack 解包投标文件（路径硬编码避免中文乱码）。"""
import sys, os

OFFICE_DIR = r"C:\Users\guangwan\.codebuddy\plugins\marketplaces\codebuddy-plugins-official\plugins\docx\scripts\office"
sys.path.insert(0, OFFICE_DIR)

import unpack as unpack_mod

SRC = r"D:\工作\投标项目\珠海海德公馆会所项目-20260618\投标文件-20260819\物资投标-亿美佳\01 珠海丹田海德公馆项目 精装修材料-投标文件.docx"
DST = r"d:\projects\cost-estimation\data\tmp\zhongbiao_unpacked"

err, msg = unpack_mod.unpack(SRC, DST, merge_runs=True, simplify_redlines=True)
print(msg)
if err:
    sys.exit(1)
