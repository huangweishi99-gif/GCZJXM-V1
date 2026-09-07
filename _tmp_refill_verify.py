# -*- coding: utf-8 -*-
"""临时：验证重填结果——成本×1.12 与控制价误差、母行链接保留、合理行未动（用后即删）。"""
import io, sys, os, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import win32com.client

CSV = r"data\tmp\重填分析报告.csv"
XLS_A = r"清单数据资料\甲方招标清单\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"
XLS_B = r"清单数据资料\甲方招标清单\云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls"
XLSX = r"清单数据资料\甲方招标清单\会所、5#6#楼公区及户内、样板间、架空层安装工程投标清单-20260825.xlsx"

rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
by_file = {"5#6#": [], "会所xls": [], "会所安装xlsx": []}
for r in rows:
    by_file[r["文件"]].append(r)

xl = win32com.client.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
try:
    # xls
    for tag, path in (("5#6#", XLS_A), ("会所xls", XLS_B)):
        wb = xl.Workbooks.Open(os.path.abspath(path), UpdateLinks=0, ReadOnly=True)
        ws = wb.Worksheets("清单表")
        recs = by_file[tag]
        max_err = 0.0
        n_changed = n_kept = 0
        bad = []
        for r in recs:
            row = int(r["行"])
            cost = ws.Cells(row, 20).Value or 0   # T
            ctrl = float(r["控制价"])
            if r["原因分类"] == "合理(±10%)":
                n_kept += 1
                continue
            n_changed += 1
            target = ctrl / 1.12
            err = (cost - target) / target * 100 if target else 0
            if abs(err) > max_err:
                max_err = abs(err)
            if abs(err) > 1:
                bad.append((row, r["项目名称"], cost, round(target, 2), round(err, 2)))
        print(f"[{tag}] 重填行={n_changed} 保留行={n_kept} 最大偏差={max_err:.3f}% 超标行={len(bad)}")
        for b in bad[:5]:
            print("   ", b)
        wb.Close(False)
    # xlsx
    wb = xl.Workbooks.Open(os.path.abspath(XLSX), UpdateLinks=0, ReadOnly=True)
    recs = by_file["会所安装xlsx"]
    max_err = 0.0
    bad = []
    for r in recs:
        ws = wb.Worksheets(r["sheet"])
        row = int(r["行"])
        cost = ws.Cells(row, 17).Value or 0   # Q
        ctrl = float(r["控制价"])
        if r["原因分类"] == "合理(±10%)":
            continue
        target = ctrl / 1.12
        err = (cost - target) / target * 100 if target else 0
        if abs(err) > max_err:
            max_err = abs(err)
        if abs(err) > 1:
            bad.append((r["sheet"], row, r["项目名称"], cost, round(target, 2), round(err, 2)))
    print(f"[会所安装xlsx] 最大偏差={max_err:.3f}% 超标行={len(bad)}")
    for b in bad[:5]:
        print("   ", b)
    wb.Close(False)
finally:
    xl.Quit()

# 抽查：母行链接公式保留 + 关键行重算结果
print("\n===== 抽查 =====")
xl2 = win32com.client.DispatchEx("Excel.Application")
xl2.Visible = False
xl2.DisplayAlerts = False
try:
    wb = xl2.Workbooks.Open(os.path.abspath(XLS_A), UpdateLinks=0, ReadOnly=True)
    ws = wb.Worksheets("清单表")
    for cell in ("T7", "U7", "W7", "X7", "Y7", "Q7", "T24", "U24", "T8", "T17", "T931"):
        v = ws.Range(cell).Value
        f = ws.Range(cell).Formula
        print(f"xls {cell}: 值={v!r} 公式={f!r}")
    wb.Close(False)
    wb = xl2.Workbooks.Open(os.path.abspath(XLS_B), UpdateLinks=0, ReadOnly=True)
    ws = wb.Worksheets("清单表")
    for cell in ("T28", "Q28", "T54", "Q54", "T450", "Q450"):
        v = ws.Range(cell).Value
        print(f"会所 {cell}: 值={v!r}")
    wb.Close(False)
finally:
    xl2.Quit()

import openpyxl
wbv = openpyxl.load_workbook(XLSX, data_only=True)
for sn, cell in (("会所售楼处消防电工程", "Q6"), ("会所售楼处消防水工程", "Q5")):
    ws = wbv[sn]
    print(f"xlsx {sn} {cell}: 值={ws[cell].value} | N(控制价)={ws['N' + cell[1:]].value}")
wbv.close()
