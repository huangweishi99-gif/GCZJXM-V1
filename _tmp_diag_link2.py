# -*- coding: utf-8 -*-
"""临时：诊断母行链接行是否被重填覆盖（先后打开，用后即删）。"""
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
        wb2 = xl.Workbooks.Open(os.path.abspath(cur), UpdateLinks=0, ReadOnly=True)
        ws2 = wb2.Worksheets("清单表")
        lost = []
        for (r, cl), f1 in bak_f.items():
            f2 = ws2.Cells(r, c if False else {"U": 21, "V": 22, "W": 23, "X": 24, "Y": 25}[cl]).Formula
            if not (isinstance(f2, str) and f2.startswith("=")):
                lost.append((r, cl, f1, ws2.Cells(r, {"U": 21, "V": 22, "W": 23, "X": 24, "Y": 25}[cl]).Value))
        wb2.Close(False)
        print(f"\n[{tag}] 链接公式被覆盖数={len(lost)}")
        for x in lost[:40]:
            print(f"   行{x[0]} {x[1]}列: 备份公式={x[2]} → 当前值={x[3]!r}")

    bak_x = {}
    for sn in ("会所售楼处消防电工程", "会所售楼处消防水工程"):
        bak_x[sn] = read_formulas(xl, BAK_X, sn, XLSX_COLS)
    wb2 = xl.Workbooks.Open(os.path.abspath(CUR_X), UpdateLinks=0, ReadOnly=True)
    for sn, bf in bak_x.items():
        ws2 = wb2.Worksheets(sn)
        lost = []
        for (r, cl), f1 in bf.items():
            c = XLSX_COLS[cl]
            f2 = ws2.Cells(r, c).Formula
            if not (isinstance(f2, str) and f2.startswith("=")):
                lost.append((r, cl, f1, ws2.Cells(r, c).Value))
        print(f"\n[xlsx {sn}] 链接公式被覆盖数={len(lost)}")
        for x in lost[:20]:
            print(f"   行{x[0]} {x[1]}列: 备份={x[2]} → 当前={x[3]!r}")
    wb2.Close(False)
finally:
    xl.Quit()
