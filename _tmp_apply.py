# -*- coding: utf-8 -*-
"""临时：把工艺测算的正确人材机成本写回三份云湾投标文件（全量：独立测算且现值≠测算的母行）。
写回 U/W/X/Y（人材机），T 成本 = U*(1+损耗率)+W+X+Y。先备份。用后即删。"""
import io, sys, os, csv, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import win32com.client

CALC = r"data\tmp\母行测算结果_全量.csv"
DIFF = r"data\tmp\母行差异分析.csv"
XLS_A = r"清单数据资料\甲方招标清单\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"
XLS_B = r"清单数据资料\甲方招标清单\云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls"
XLSX = r"清单数据资料\甲方招标清单\会所、5#6#楼公区及户内、样板间、架空层安装工程投标清单-20260825.xlsx"
BAK = r"data\tmp\云湾全量重组前备份-20260825"
os.makedirs(BAK, exist_ok=True)
for p in (XLS_A, XLS_B, XLSX):
    d = os.path.join(BAK, os.path.basename(p))
    if not os.path.exists(d):
        shutil.copy2(p, d)
        print("已备份 ->", d)

# 损耗率映射 (文件,sheet,行) -> V
loss = {}
for r in csv.DictReader(open(DIFF, encoding="utf-8-sig")):
    loss[(r["文件"], r.get("sheet", ""), r["行"])] = float(r["损耗率V"] or 0)

rows = list(csv.DictReader(open(CALC, encoding="utf-8-sig")))
todo = []
for r in rows:
    if r["兜底"] == "Y":
        continue  # 定制柜/成品家具按控制价拆分，无独立测算基础，保持现值
    cur = float(r["现成本"] or 0)
    new = float(r["新成本"] or 0)
    if not cur:
        continue
    if abs(cur - new) / cur <= 0.01:
        continue
    todo.append(r)
print(f"测算记录 {len(rows)}，需重填(独立测算且现值≠测算) {len(todo)} 条")

COLS = {
    "xls": {"u": 21, "w": 23, "x": 24, "y": 25, "t": 20},
    "xlsx": {"u": 18, "w": 20, "x": 21, "y": 22, "t": 17},
}
by = {}
for r in todo:
    by.setdefault((r["文件"], r.get("sheet", "")), []).append(r)

xl = win32com.client.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
try:
    for tag, path, sheet in (("5#6#", XLS_A, "清单表"), ("会所xls", XLS_B, "清单表"),
                             ("会所安装xlsx", XLSX, None)):
        keys = [k for k in by if k[0] == tag]
        if not keys:
            print(f"[{tag}] 无修改")
            continue
        wb = xl.Workbooks.Open(os.path.abspath(path), UpdateLinks=0, ReadOnly=False)
        total = 0
        for (_, sn), lst in by.items():
            if _ != tag:
                continue
            ws = wb.Worksheets(sn)
            cc = COLS["xls"] if tag != "会所安装xlsx" else COLS["xlsx"]
            for r in lst:
                row = int(r["行"])
                u = float(r["新主材"] or 0); w = float(r["新人工"] or 0)
                x = float(r["新辅材"] or 0); y = float(r["新机械"] or 0)
                v = loss.get((tag, sn, str(row)), 0)
                t = round(u * (1 + v) + w + x + y, 2)
                ws.Cells(row, cc["u"]).Value = u
                ws.Cells(row, cc["w"]).Value = w
                ws.Cells(row, cc["x"]).Value = x
                ws.Cells(row, cc["y"]).Value = y
                ws.Cells(row, cc["t"]).Value = t
                total += 1
        wb.Save()
        wb.Close(True)
        print(f"[{tag}] 写回 {total} 行")
finally:
    xl.Quit()
print("写回完成")
