# -*- coding: utf-8 -*-
"""临时：抽查异常行完整列数据（H~Z / G~W），用后即删。"""
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import win32com.client
from openpyxl.utils import get_column_letter

XLS_A = r"清单数据资料\甲方招标清单\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"
XLS_B = r"清单数据资料\甲方招标清单\云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls"
XLSX = r"清单数据资料\甲方招标清单\会所、5#6#楼公区及户内、样板间、架空层安装工程投标清单-20260825.xlsx"

xl = win32com.client.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
try:
    for tag, path, rows_ in (("5#6#", XLS_A, (17, 160, 474, 931, 1119)), ("会所xls", XLS_B, (28, 54, 450, 586))):
        print("\n##########", tag)
        wb = xl.Workbooks.Open(os.path.abspath(path), UpdateLinks=0, ReadOnly=True)
        ws = wb.Worksheets("清单表")
        for r in rows_:
            vals = []
            for c in range(7, 27):  # G~Z
                v = ws.Cells(r, c).Value
                if v is not None:
                    s = str(v).replace("\n", "⏎")[:28]
                    vals.append(f"{get_column_letter(c)}={s}")
            print(f"行{r} | " + " | ".join(vals))
        wb.Close(False)
finally:
    xl.Quit()

print("\n########## xlsx 消防电 异常行")
import openpyxl
wbv = openpyxl.load_workbook(XLSX, data_only=True)
for sn, rows_ in (("会所售楼处消防电工程", (6, 19)), ("会所售楼处消防水工程", (5,))):
    ws = wbv[sn]
    print(f"\n## {sn}")
    for r in rows_:
        vals = []
        for c in range(6, 24):  # F~W
            v = ws.cell(row=r, column=c).value
            if v is not None:
                s = str(v).replace("\n", "⏎")[:28]
                vals.append(f"{get_column_letter(c)}={s}")
        print(f"行{r} | " + " | ".join(vals))
wbv.close()
