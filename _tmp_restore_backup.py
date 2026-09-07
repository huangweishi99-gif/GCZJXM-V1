# -*- coding: utf-8 -*-
"""临时：从备份恢复三份云湾文件（撤销倒推重填），用后即删。"""
import io, sys, os, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BAK = r"data\tmp\云湾控制价校准前备份"
FILES = [
    "云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls",
    "云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls",
    "会所、5#6#楼公区及户内、样板间、架空层安装工程投标清单-20260825.xlsx",
]
DST = r"清单数据资料\甲方招标清单"
for f in FILES:
    src = os.path.join(BAK, f)
    dst = os.path.join(DST, f)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print("已恢复 ->", dst)
    else:
        print("备份缺失:", src)
