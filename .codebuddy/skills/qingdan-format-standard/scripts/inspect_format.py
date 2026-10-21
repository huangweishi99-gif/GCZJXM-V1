"""inspect_format.py — 提取 Excel 簿格式诊断信息（打印设置/字体/列宽/公式数）。
用法: python inspect_format.py <文件.xls|xlsx> [--sheet 名]
只读打开，不修改文件。GBK 控制台已处理。
"""
import sys

import win32com.client


def main():
    if len(sys.argv) < 2:
        print("用法: python inspect_format.py <文件> [--sheet 名]")
        sys.exit(1)
    fp = sys.argv[1]
    only_sheet = sys.argv[sys.argv.index("--sheet") + 1] if "--sheet" in sys.argv else None

    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(fp, ReadOnly=True)
        for i in range(1, wb.Worksheets.Count + 1):
            ws = wb.Worksheets(i)
            if only_sheet and ws.Name != only_sheet:
                continue
            ps = ws.PageSetup
            f_cnt = 0
            for row in ws.UsedRange.Rows:
                for c in row.Cells:
                    if c.HasFormula:
                        f_cnt += 1
                    if f_cnt >= 99999:
                        break
            # 表头探测：前5行非空单元格
            heads = []
            for r in range(1, min(6, ws.UsedRange.Rows.Count + 1)):
                vals = [ws.Cells(r, cc).Value for cc in range(1, min(8, ws.UsedRange.Columns.Count + 1))]
                heads.append(f"行{r}:" + "/".join(str(v)[:8] for v in vals if v not in (None, "")))
            print(f"== {ws.Name}  used={ws.UsedRange.Address}  公式数={f_cnt}")
            print(f"   打印区域={ps.PrintArea!r}  纸张={ps.PaperSize} 方向={ps.Orientation} "
                  f"FitWide={ps.FitToPagesWide} 标题行={ps.PrintTitleRows!r}")
            print(f"   页脚C={ps.CenterFooter!r} 边距T/B/L/R={ps.TopMargin}/{ps.BottomMargin}/{ps.LeftMargin}/{ps.RightMargin}")
            print(f"   字体: 标题A1={ws.Range('A1').Font.Name}/{ws.Range('A1').Font.Size}  "
                  f"数据A5={ws.Range('A5').Font.Name}/{ws.Range('A5').Font.Size}")
            for h in heads:
                if h.strip() not in ("行1:", "行2:", "行3:", "行4:", "行5:"):
                    print(f"   {h}")
        wb.Close(False)
    finally:
        excel.Quit()


if __name__ == "__main__":
    main()
