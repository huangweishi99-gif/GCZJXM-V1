"""apply_standard_format.py — 对既有簿批量套用标准打印设置（不动数据/样式/公式）。
用法: python apply_standard_format.py <文件> [--apply]
不加 --apply 时只打印每个 sheet 的现状与将套用的参数（dry-run）。
标准：A4 横向 / 1页宽 / 标题行$1:$5 / 打印区域=UsedRange / 页脚 第&P页共&N页 / 边距42.5/42.5/42.5/28.3 / 水平居中。
"""
import sys

import win32com.client


def apply(ws):
    ps = ws.PageSetup
    ps.PaperSize = 9            # A4
    ps.Orientation = 2          # 横向
    ps.Zoom = False
    ps.FitToPagesWide = 1
    ps.FitToPagesTall = False
    last = ws.Cells(ws.UsedRange.Rows.Count + ws.UsedRange.Row - 1,
                    ws.UsedRange.Columns.Count + ws.UsedRange.Column - 1).Address
    first = ws.Cells(ws.UsedRange.Row, ws.UsedRange.Column).Address
    ps.PrintArea = f"{first}:{last}"
    ps.PrintTitleRows = "$1:$5"
    ps.TopMargin = 42.5
    ps.BottomMargin = 42.5
    ps.LeftMargin = 42.5
    ps.RightMargin = 28.3
    ps.CenterHorizontally = True
    ps.CenterFooter = "第 &P 页，共 &N 页"
    ps.PrintGridlines = False


def main():
    if len(sys.argv) < 2:
        print("用法: python apply_standard_format.py <文件> [--apply]")
        sys.exit(1)
    fp = sys.argv[1]
    do_apply = "--apply" in sys.argv

    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(fp)
        for i in range(1, wb.Worksheets.Count + 1):
            ws = wb.Worksheets(i)
            print(f"[{'APPLY' if do_apply else 'DRY'}] {ws.Name}: "
                  f"区域{ws.PageSetup.PrintArea!r} 方向{ws.PageSetup.Orientation} -> A4横向/标题$1:$5")
            if do_apply:
                apply(ws)
        if do_apply:
            wb.Save()
            print("已保存。请用 inspect_format.py 复查。")
        wb.Close(False)
    finally:
        excel.Quit()


if __name__ == "__main__":
    main()
