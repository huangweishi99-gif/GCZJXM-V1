# -*- coding: utf-8 -*-
"""临时：提取关键母行的项目特征，确认甲供/规格（用后即删）。"""
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import win32com.client

XLS_A = r"清单数据资料\甲方招标清单\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"
XLS_B = r"清单数据资料\甲方招标清单\云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls"

xl = win32com.client.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
try:
    wb = xl.Workbooks.Open(os.path.abspath(XLS_A), UpdateLinks=0, ReadOnly=True)
    ws = wb.Worksheets("清单表")
    rows = [7, 8, 9, 13, 26, 29, 35, 39, 41, 55, 109, 113, 159, 161, 165, 195, 202, 417, 441, 483, 526, 591, 613, 676, 852, 927, 928, 1093, 1094, 1148, 1118, 1119, 1101, 1164]
    print("===== 5#6# 关键行特征 =====")
    for r in rows:
        name = str(ws.Cells(r, 2).Value or "")
        feat = str(ws.Cells(r, 3).Value or "")
        unit = ws.Cells(r, 6).Value
        qty = ws.Cells(r, 7).Value
        print(f"行{r}: [{name}] 单位={unit} 量={qty}")
        print(f"    特征: {feat[:120]}")
    wb.Close(False)
    wb = xl.Workbooks.Open(os.path.abspath(XLS_B), UpdateLinks=0, ReadOnly=True)
    ws = wb.Worksheets("清单表")
    rows = [22, 27, 28, 38, 79, 89, 147, 185, 224, 229, 239, 315, 329, 447, 456, 466, 480, 543, 586, 589, 596]
    print("\n===== 会所 关键行特征 =====")
    for r in rows:
        name = str(ws.Cells(r, 2).Value or "")
        feat = str(ws.Cells(r, 3).Value or "")
        unit = ws.Cells(r, 6).Value
        qty = ws.Cells(r, 7).Value
        print(f"行{r}: [{name}] 单位={unit} 量={qty}")
        print(f"    特征: {feat[:120]}")
    wb.Close(False)
finally:
    xl.Quit()
