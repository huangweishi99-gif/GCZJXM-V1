# -*- coding: utf-8 -*-
"""临时：从备份恢复被覆盖的母行链接公式（U/W/X/Y 列），用后即删。"""
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import win32com.client

BAK_A = r"data\tmp\云湾控制价校准前备份\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"
CUR_A = r"清单数据资料\甲方招标清单\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"
BAK_B = r"data\tmp\云湾控制价校准前备份\云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls"
CUR_B = r"清单数据资料\甲方招标清单\云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls"
BAK_X = r"data\tmp\云湾控制价校准前备份\会所、5#6#楼公区及户内、样板间、架空层安装工程投标清单-20260825.xlsx"
CUR_X = r"清单数据资料\甲方招标清单\会所、5#6#楼公区及户内、样板间、架空层安装工程投标清单-20260825.xlsx"

XLS_COLS = {"U": 21, "V": 22, "W": 23, "X": 24, "Y": 25}
XLSX_COLS = {"R": 18, "S": 19, "T": 20, "U": 21, "V": 22}


def read_formulas(xl, path, sheet, cols):
    wb = xl.Workbooks.Open(os.path.abspath(path), UpdateLinks=0, ReadOnly=True)
    ws = wb.Worksheets(sheet)
    ur = ws.UsedRange
    out = {}
    for i in range(1, ur.Rows.Count + 1):
        r = ur.Row + i - 1
        for cl, c in cols.items():
            f = ws.Cells(r, c).Formula
            if isinstance(f, str) and f.startswith("="):
                out[(r, cl)] = f
    wb.Close(False)
    return out


xl = win32com.client.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
try:
    for tag, bak, cur, cols in (("5#6#", BAK_A, CUR_A, XLS_COLS), ("会所xls", BAK_B, CUR_B, XLS_COLS)):
        bak_f = read_formulas(xl, bak, "清单表", cols)
        wb = xl.Workbooks.Open(os.path.abspath(cur), UpdateLinks=0, ReadOnly=False)
        ws = wb.Worksheets("清单表")
        n_restore = 0
        for (r, cl), f1 in bak_f.items():
            c = cols[cl]
            f2 = ws.Cells(r, c).Formula
            if not (isinstance(f2, str) and f2.startswith("=")):
                ws.Cells(r, c).Formula = f1
                n_restore += 1
        wb.Save()
        wb.Close(True)
        print(f"[{tag}] 恢复链接公式 {n_restore} 个")
finally:
    xl.Quit()

# xlsx 消防
xl2 = win32com.client.DispatchEx("Excel.Application")
xl2.Visible = False
xl2.DisplayAlerts = False
try:
    bak_fs = {}
    for sn in ("会所售楼处消防电工程", "会所售楼处消防水工程"):
        bak_fs[sn] = read_formulas(xl2, BAK_X, sn, XLSX_COLS)
    wb = xl2.Workbooks.Open(os.path.abspath(CUR_X), UpdateLinks=0, ReadOnly=False)
    for sn, bf in bak_fs.items():
        ws = wb.Worksheets(sn)
        n_restore = 0
        for (r, cl), f1 in bf.items():
            c = XLSX_COLS[cl]
            f2 = ws.Cells(r, c).Formula
            if not (isinstance(f2, str) and f2.startswith("=")):
                ws.Cells(r, c).Formula = f1
                n_restore += 1
        print(f"[xlsx {sn}] 恢复链接公式 {n_restore} 个")
    wb.Save()
    wb.Close(True)
finally:
    xl2.Quit()
print("修复完成")
