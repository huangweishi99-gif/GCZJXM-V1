# -*- coding: utf-8 -*-
"""临时：诊断母行链接行是否被重填覆盖（用后即删）。"""
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import win32com.client
from openpyxl.utils import get_column_letter

BAK_A = r"data\tmp\云湾控制价校准前备份\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"
CUR_A = r"清单数据资料\甲方招标清单\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"
BAK_B = r"data\tmp\云湾控制价校准前备份\云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls"
CUR_B = r"清单数据资料\甲方招标清单\云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls"
BAK_X = r"data\tmp\云湾控制价校准前备份\会所、5#6#楼公区及户内、样板间、架空层安装工程投标清单-20260825.xlsx"
CUR_X = r"清单数据资料\甲方招标清单\会所、5#6#楼公区及户内、样板间、架空层安装工程投标清单-20260825.xlsx"

# 成本区列：xls U/W/X/Y = 21,23,24,25 ；xlsx 消防 R/T/U/V = 18,20,21,22
XLS_COLS = {"U": 21, "V": 22, "W": 23, "X": 24, "Y": 25}
XLSX_COLS = {"R": 18, "S": 19, "T": 20, "U": 21, "V": 22}

xl = win32com.client.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
try:
    for tag, bak, cur, cols in (
        ("5#6#", BAK_A, CUR_A, XLS_COLS), ("会所xls", BAK_B, CUR_B, XLS_COLS)):
        wb1 = xl.Workbooks.Open(os.path.abspath(bak), UpdateLinks=0, ReadOnly=True)
        ws1 = wb1.Worksheets("清单表")
        wb2 = xl.Workbooks.Open(os.path.abspath(cur), UpdateLinks=0, ReadOnly=True)
        ws2 = wb2.Worksheets("清单表")
        ur = ws1.UsedRange
        lost = []  # (行, 列, 备份公式, 当前)
        for i in range(1, ur.Rows.Count + 1):
            r = ur.Row + i - 1
            for cl, c in cols.items():
                f1 = ws1.Cells(r, c).Formula
                v2 = ws2.Cells(r, c).Value
                if isinstance(f1, str) and f1.startswith("="):
                    # 备份里是公式（母行链接），检查当前是否被覆盖为数值
                    f2 = ws2.Cells(r, c).Formula
                    if not (isinstance(f2, str) and f2.startswith("=")):
                        lost.append((r, cl, f1, v2))
        print(f"\n[{tag}] 链接公式被覆盖数={len(lost)}")
        for x in lost[:30]:
            print(f"   行{x[0]} {x[1]}列: 备份公式={x[2]} → 当前值={x[3]!r}")
        wb1.Close(False); wb2.Close(False)
    # xlsx 消防
    wb1 = xl.Workbooks.Open(os.path.abspath(BAK_X), UpdateLinks=0, ReadOnly=True)
    wb2 = xl.Workbooks.Open(os.path.abspath(CUR_X), UpdateLinks=0, ReadOnly=True)
    for sn in ("会所售楼处消防电工程", "会所售楼处消防水工程"):
        ws1, ws2 = wb1.Worksheets(sn), wb2.Worksheets(sn)
        lost = []
        for r in range(1, ws1.UsedRange.Rows.Count + 1):
            for cl, c in XLSX_COLS.items():
                f1 = ws1.Cells(r, c).Formula
                if isinstance(f1, str) and f1.startswith("="):
                    f2 = ws2.Cells(r, c).Formula
                    if not (isinstance(f2, str) and f2.startswith("=")):
                        lost.append((r, cl, f1, ws2.Cells(r, c).Value))
        print(f"\n[xlsx {sn}] 链接公式被覆盖数={len(lost)}")
        for x in lost[:20]:
            print(f"   行{x[0]} {x[1]}列: 备份={x[2]} → 当前={x[3]!r}")
    wb1.Close(False); wb2.Close(False)
finally:
    xl.Quit()
