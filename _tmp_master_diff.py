# -*- coding: utf-8 -*-
"""临时：识别母行（U/W/X/Y 为数值），统计母行成本×1.12 与控制价差异，用后即删。"""
import io, sys, os, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import win32com.client

XLS_A = r"清单数据资料\甲方招标清单\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"
XLS_B = r"清单数据资料\甲方招标清单\云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls"
XLSX = r"清单数据资料\甲方招标清单\会所、5#6#楼公区及户内、样板间、架空层安装工程投标清单-20260825.xlsx"
OUT = r"data\tmp\母行差异分析.csv"

xl = win32com.client.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
recs = []
try:
    for tag, path in (("5#6#", XLS_A), ("会所xls", XLS_B)):
        wb = xl.Workbooks.Open(os.path.abspath(path), UpdateLinks=0, ReadOnly=True)
        ws = wb.Worksheets("清单表")
        ur = ws.UsedRange
        for i in range(1, ur.Rows.Count + 1):
            r = ur.Row + i - 1
            a = ws.Cells(r, 1).Value
            if not isinstance(a, (int, float)):
                continue
            # 母行判定：U/W/X/Y(21,23,24,25) 均为数值；有公式则链接行
            is_master = True
            for c in (21, 23, 24, 25):
                f = ws.Cells(r, c).Formula
                if isinstance(f, str) and f.startswith("="):
                    is_master = False
                    break
            name = str(ws.Cells(r, 2).Value or "")[:40]
            feat = str(ws.Cells(r, 3).Value or "")[:90]
            unit = ws.Cells(r, 6).Value or ""
            qty = ws.Cells(r, 7).Value or 0
            cost = ws.Cells(r, 20).Value or 0    # T 成本
            ctrl = ws.Cells(r, 17).Value or 0    # Q 控制价
            u = ws.Cells(r, 21).Value or 0; v = ws.Cells(r, 22).Value or 0
            w = ws.Cells(r, 23).Value or 0; x = ws.Cells(r, 24).Value or 0
            y = ws.Cells(r, 25).Value or 0
            cost *= 1.0; ctrl *= 1.0
            ratio = (cost * 1.12 / ctrl) if ctrl else None
            diff = round((ratio - 1) * 100, 1) if ratio else None
            recs.append({
                "文件": tag, "行": r, "sheet": "清单表", "类型": "母行" if is_master else "链接行",
                "项目名称": name, "单位": str(unit), "工程量": qty,
                "成本": round(cost, 2), "成本x1.12": round(cost * 1.12, 2),
                "控制价": round(ctrl, 2), "差异%": diff,
                "主材U": round(u, 2), "损耗率V": v, "人工W": round(w, 2),
                "辅材X": round(x, 2), "机械Y": round(y, 2),
                "特征": feat,
            })
        wb.Close(False)
    # xlsx 消防
    wb = xl.Workbooks.Open(os.path.abspath(XLSX), UpdateLinks=0, ReadOnly=True)
    for sn in ("会所售楼处消防电工程", "会所售楼处消防水工程"):
        ws = wb.Worksheets(sn)
        ur = ws.UsedRange
        for i in range(1, ur.Rows.Count + 1):
            r = ur.Row + i - 1
            a = ws.Cells(r, 1).Value
            if not isinstance(a, (int, float)):
                continue
            is_master = True
            for c in (18, 20, 21, 22):  # R,T,U,V
                f = ws.Cells(r, c).Formula
                if isinstance(f, str) and f.startswith("="):
                    is_master = False
                    break
            name = str(ws.Cells(r, 3).Value or "")[:40]
            feat = str(ws.Cells(r, 4).Value or "")[:90]
            unit = ws.Cells(r, 5).Value or ""
            qty = ws.Cells(r, 6).Value or 0
            cost = ws.Cells(r, 17).Value or 0   # Q
            ctrl = ws.Cells(r, 14).Value or 0   # N
            u = ws.Cells(r, 18).Value or 0; v = ws.Cells(r, 19).Value or 0
            w = ws.Cells(r, 20).Value or 0; x = ws.Cells(r, 21).Value or 0
            y = ws.Cells(r, 22).Value or 0
            cost *= 1.0; ctrl *= 1.0
            ratio = (cost * 1.12 / ctrl) if ctrl else None
            diff = round((ratio - 1) * 100, 1) if ratio else None
            recs.append({
                "文件": "会所安装xlsx", "行": r, "sheet": sn, "类型": "母行" if is_master else "链接行",
                "项目名称": name, "单位": str(unit), "工程量": qty,
                "成本": round(cost, 2), "成本x1.12": round(cost * 1.12, 2),
                "控制价": round(ctrl, 2), "差异%": diff,
                "主材U": round(u, 2), "损耗率V": v, "人工W": round(w, 2),
                "辅材X": round(x, 2), "机械Y": round(y, 2),
                "特征": feat,
            })
    wb.Close(False)
finally:
    xl.Quit()

with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
    w.writeheader()
    for r in recs:
        w.writerow(r)

masters = [r for r in recs if r["类型"] == "母行"]
links = [r for r in recs if r["类型"] == "链接行"]
print(f"总行={len(recs)} 母行={len(masters)} 链接行={len(links)}")
for tag in ("5#6#", "会所xls", "会所安装xlsx"):
    ms = [r for r in masters if r["文件"] == tag]
    print(f"[{tag}] 母行={len(ms)}")
    import collections
    def bucket(d):
        if d is None: return "异常"
        a = abs(d)
        if a <= 10: return "±10%"
        if a <= 30: return "10~30%"
        if a <= 100: return "30~100%"
        return ">100%"
    c = collections.Counter(bucket(r["差异%"]) for r in ms)
    print("   差异分布:", dict(c))
print("CSV ->", OUT)
