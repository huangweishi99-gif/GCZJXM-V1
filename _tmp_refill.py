# -*- coding: utf-8 -*-
"""临时：按控制价重填三份云湾文件成本（只改数据行成本区，母行链接自动跟随），用后即删。

规则：新成本单价 = 控制价 / 1.12；结构按原比例缩放；主材吸收舍入；漏填项按 主材50%/人工35%/辅材15%。
"""
import io, sys, os, csv, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import win32com.client

CSV = r"data\tmp\重填分析报告.csv"
XLS_A = r"清单数据资料\甲方招标清单\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"
XLS_B = r"清单数据资料\甲方招标清单\云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260825.xls"
XLSX = r"清单数据资料\甲方招标清单\会所、5#6#楼公区及户内、样板间、架空层安装工程投标清单-20260825.xlsx"
BAK = r"data\tmp\云湾控制价校准前备份"
os.makedirs(BAK, exist_ok=True)
for p in (XLS_A, XLS_B, XLSX):
    d = os.path.join(BAK, os.path.basename(p))
    if not os.path.exists(d):
        shutil.copy2(p, d)
        print("已备份 ->", d)

rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
print(f"分析记录 {len(rows)} 条")

# 列映射：文件 -> (sheet 关键字, 主材列, 损耗率列, 人工列, 辅材列, 机械列)
# xls: U=21,V=22,W=23,X=24,Y=25 ；xlsx 消防: R=18,S=19,T=20,U=21,V=22
COLS = {
    "xls": {"u": 21, "v": 22, "w": 23, "x": 24, "y": 25},
    "xlsx": {"u": 18, "v": 19, "w": 20, "x": 21, "y": 22},
}


def calc(target, u, v, w, x, y, cost):
    """返回 (u2,w2,x2,y2)。cost>0 时整体缩放；cost<=0 时按占比补齐。"""
    if cost and cost > 0:
        scale = target / cost
        w2 = round(w * scale, 2)
        x2 = round(x * scale, 2)
        y2 = round(y * scale, 2)
        denom = (1 + v) if v else 1.0
        u2 = round((target - w2 - x2 - y2) / denom, 2)
        if u2 < 0:
            u2 = 0.0
        return u2, w2, x2, y2
    w2 = round(target * 0.35, 2)
    x2 = round(target * 0.15, 2)
    y2 = 0.0
    u2 = round(target - w2 - x2, 2)
    return u2, w2, x2, y2


# 分文件组织待改记录
by_file = {"5#6#": [], "会所xls": [], "会所安装xlsx": []}
for r in rows:
    if r["原因分类"] == "合理(±10%)":
        continue
    by_file[r["文件"]].append(r)

xl = win32com.client.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
try:
    # ---- xls 两文件 ----
    for tag, path in (("5#6#", XLS_A), ("会所xls", XLS_B)):
        recs = by_file[tag]
        if not recs:
            print(f"[{tag}] 无修改")
            continue
        wb = xl.Workbooks.Open(os.path.abspath(path), UpdateLinks=0, ReadOnly=False)
        ws = wb.Worksheets("清单表")
        changed = 0
        for r in recs:
            row = int(r["行"])
            target = float(r["建议新成本"])
            u = float(r["原主材"] or 0); v = float(r["损耗率"] or 0)
            w = float(r["原人工"] or 0); x = float(r["原辅材"] or 0)
            y = float(r["原机械"] or 0); cost = float(r["成本单价"] or 0)
            u2, w2, x2, y2 = calc(target, u, v, w, x, y, cost)
            # 写入（原值为空且新值为0时跳过）
            for col, val, old in ((COLS["xls"]["u"], u2, u), (COLS["xls"]["w"], w2, w),
                                  (COLS["xls"]["x"], x2, x), (COLS["xls"]["y"], y2, y)):
                if val == 0 and old == 0 and ws.Cells(row, col).Value in (None, ""):
                    continue
                ws.Cells(row, col).Value = val
            changed += 1
        wb.Save()
        wb.Close(True)
        print(f"[{tag}] 重填 {changed} 行")
    # ---- xlsx 消防电/消防水 ----
    recs = by_file["会所安装xlsx"]
    if recs:
        wb = xl.Workbooks.Open(os.path.abspath(XLSX), UpdateLinks=0, ReadOnly=False)
        per = {}
        for r in recs:
            per.setdefault(r["sheet"], []).append(r)
        for sn, lst in per.items():
            ws = wb.Worksheets(sn)
            for r in lst:
                row = int(r["行"])
                target = float(r["建议新成本"])
                u = float(r["原主材"] or 0); v = float(r["损耗率"] or 0)
                w = float(r["原人工"] or 0); x = float(r["原辅材"] or 0)
                y = float(r["原机械"] or 0); cost = float(r["成本单价"] or 0)
                u2, w2, x2, y2 = calc(target, u, v, w, x, y, cost)
                for col, val in ((COLS["xlsx"]["u"], u2), (COLS["xlsx"]["w"], w2),
                                 (COLS["xlsx"]["x"], x2), (COLS["xlsx"]["y"], y2)):
                    ws.Cells(row, col).Value = val
            print(f"[会所安装xlsx] sheet={sn} 重填 {len(lst)} 行")
        wb.Save()
        wb.Close(True)
finally:
    xl.Quit()
print("重填完成")
