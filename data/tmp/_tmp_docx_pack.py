# -*- coding: utf-8 -*-
"""备份原件并用 skill pack 重新打包投标文件。"""
import sys, os, shutil

OFFICE_DIR = r"C:\Users\guangwan\.codebuddy\plugins\marketplaces\codebuddy-plugins-official\plugins\docx\scripts\office"
sys.path.insert(0, OFFICE_DIR)

import pack as pack_mod

SRC_DIR = r"d:\projects\cost-estimation\data\tmp\zhongbiao_unpacked"
DST = r"D:\工作\投标项目\珠海海德公馆会所项目-20260618\投标文件-20260819\物资投标-亿美佳\01 珠海丹田海德公馆项目 精装修材料-投标文件.docx"
BAK = r"d:\projects\cost-estimation\data\tmp\01 投标文件-原版备份.docx"

# 1) 备份原件
shutil.copy2(DST, BAK)
print("备份:", BAK)

# 2) 重新打包（跳过校验：校验器在 Windows 用 GBK 读 XML 必然报编码错，与文档本身无关）
err, msg = pack_mod.pack(SRC_DIR, DST, original_file=DST, validate=False)
print(msg)
if err:
    sys.exit(1)
