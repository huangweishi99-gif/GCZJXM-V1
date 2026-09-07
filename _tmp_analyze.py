# -*- coding: utf-8 -*-
"""临时：提取三份云湾文件所有清单行，对比 成本×1.12 vs 控制价，输出 CSV（用后即删）。"""
import io, sys, os, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import win32com.client
from openpyxl.utils import get_column_letter

XLS_A = r"清单数据资料\甲方招标清单\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"
XLS_B = r"清单数据资料\甲方招标清单\云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls"
XLSX = r"清单数据资料\甲方招标清单\会所、5#6#楼公区及户内、样板间、架空层安装工程投标清单-20260825.xlsx"
OUT = r"data\tmp\控制价对比分析.csv"

rows = []


def add(tag, sheet, row, name, unit, qty, cost, ctrl, note=""):
    ratio = (cost * 1.12 / ctrl) if (ctrl and ctrl > 0 and cost) else None
    rows.append({
        "文件": tag, "sheet": sheet, "行": row,
        "项目名称": name, "单位": unit, "工程量": qty,
        "成本单价": cost, "控制价": ctrl, "成本x1.12": cost * 1.12 if cost else None,
        "比值(成本x1.12/控制价)": round(ratio, 3) if ratio else "",
        "差异%": round((ratio - 1) * 100, 1) if ratio else "",
        "备注": note,
    })


# ---- xls 两文件 ----
xl = win32com.client.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
try:
    for tag, path in (("5#6#", XLS_A), ("会所xls", XLS_B)):
        wb = xl.Workbooks.Open(os.path.abspath(path), UpdateLinks=0, ReadOnly=True)
        ws = wb.Worksheets("清单表")
        ur = ws.UsedRange
        n_r, n_c = ur.Rows.Count, ur.Columns.Count
        # 缓存整表值
        val = ur.Value
        for i in range(n_r):
            r = ur.Row + i
            a = val[i][0] if isinstance(val[i], tuple) else val[i]
            if not isinstance(a, (int, float)):
                continue
            def g(c):
                v = val[i][c - 1] if isinstance(val[i], tuple) else None
                return v
            name = g(2) or ""
            unit = g(6) or ""
            qty = g(7) or 0
            cost = g(20) or 0      # T 列成本单价
            ctrl = g(17) or 0      # Q 列控制价
            if name:
                add(tag, "清单表", r, str(name)[:24], unit, qty,
                    cost if isinstance(cost, (int, float)) else 0,
                    ctrl if isinstance(ctrl, (int, float)) else 0)
        wb.Close(False)
finally:
    xl.Quit()

# ---- xlsx 消防电/消防水 ----
import openpyxl
wbv = openpyxl.load_workbook(XLSX, data_only=True)
for sn in ("会所售楼处消防电工程", "会所售楼处消防水工程"):
    ws = wbv[sn]
    for r in range(5, ws.max_row + 1):
        a = ws.cell(row=r, column=1).value
        if not isinstance(a, (int, float)):
            continue
        name = ws.cell(row=r, column=3).value or ""
        unit = ws.cell(row=r, column=5).value or ""
        qty = ws.cell(row=r, column=6).value or 0
        cost = ws.cell(row=r, column=17).value or 0   # Q 列
        ctrl = ws.cell(row=r, column=14).value or 0   # N 列
        if not isinstance(cost, (int, float)) or not isinstance(ctrl, (int, float)):
            continue
        add("会所安装xlsx", sn, r, str(name)[:24], unit, qty, cost, ctrl)
wbv.close()

with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    for r in rows:
        w.writerow(r)

print(f"共 {len(rows)} 个清单行 -> {OUT}")
# 快速统计：按 |差异%| 分级
bins = {"|diff|<=5%": 0, "5~10%": 0, "10~30%": 0, "30~100%": 0, ">100% 或反向": 0}
for r in rows:
    d = r["差异%"]
    if d == "":
        bins[">100% 或反向"] += 1
    else:
        ad = abs(d)
        if ad <= 5: bins["|diff|<=5%"] += 1
        elif ad <= 10: bins["5~10%"] += 1
        elif ad <= 30: bins["10~30%"] += 1
        elif ad <= 100: bins["30~100%"] += 1
        else: bins[">100% 或反向"] += 1
for k, v in bins.items():
    print(f"  {k}: {v}")
