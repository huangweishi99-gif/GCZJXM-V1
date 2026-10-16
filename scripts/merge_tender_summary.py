# -*- coding: utf-8 -*-
"""把项目的各 -整理清单 按汇总表顺序合并进汇总表工作簿，并连接 D 列成本分析金额。

用法：
    python scripts/merge_tender_summary.py <汇总表.xls> [--out <输出.xls>]

逻辑：
1. 解析汇总表 B 列：凡是「名称含 - / — 分隔 + C 列有数值」的行视为单位工程行，
   取其名称最后一段（如「福永...-拆除工程」→「拆除工程」）为匹配后缀；
2. 在汇总表所在项目目录递归找 ``*{后缀}*-整理清单.xls``，同名多份时优先
   不含「原始清单」的版本（用户手工版优先）；
3. 按汇总表行顺序把各清单 sheet 复制进汇总簿（位置参数 Copy，命名参数会被
   pywin32 静默忽略），复制后断言 sheet 数 +1；
4. D 列写同簿全绝对引用 ='{sheet名}'!$Q${末行}（末行=含税建安工程造价行），
   与汇总表 C 列招标控制金额（含税口径）对比。小计/合计行公式不动。

依赖 pywin32 + Excel。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path

import win32com.client as wc

# 汇总表里非单位工程的行名特征（小计/合计/其他费），跳过
_SKIP_WORDS = ("小计", "合计", "其他费", "暂列", "总计")


def _short_suffix(name: str) -> str:
    """取单位工程名称最后一段：'福永...-拆除工程' / '福永...—标识系统' → 后缀。"""
    for sep in ("-", "—", "–"):
        if sep in name:
            return name.rsplit(sep, 1)[-1].strip()
    return ""


def parse_summary_rows(ws) -> list[tuple[int, str, str]]:
    """返回 [(汇总表行号, 单位工程全名, 后缀)]，按行号升序。"""
    out = []
    n = ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1
    for r in range(4, n + 1):
        b = ws.Cells(r, 2).Value
        c = ws.Cells(r, 3).Value
        if not isinstance(b, str) or not b.strip():
            continue
        name = b.strip()
        if any(w in name for w in _SKIP_WORDS):
            continue
        if not isinstance(c, (int, float)):
            continue
        suffix = _short_suffix(name)
        # 名称必须带项目前缀分隔（防止把纯备注行当单位工程）
        if suffix and suffix != name:
            out.append((r, name, suffix))
    return out


def find_tender_file(root: Path, suffix: str) -> Path:
    cands = [p for p in root.rglob(f"*{suffix}*-整理清单.xls")
             if p.is_file() and "汇总表" not in p.name]
    if not cands:
        raise FileNotFoundError(f"找不到 {suffix} 的整理清单（*{suffix}*-整理清单.xls）")
    # 同名多份（如手工版 + 从原始清单生成的版）优先不含「原始清单」的
    cands.sort(key=lambda p: "原始清单" in p.name)
    return cands[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("summary", help="汇总表 .xls 路径")
    ap.add_argument("--out", help="输出路径（默认 <汇总表>-成本分析.xls，不覆盖原件）")
    args = ap.parse_args()

    summary = Path(args.summary).resolve()
    root = summary.parent
    out = Path(args.out).resolve() if args.out else summary.with_name(
        summary.stem + "-成本分析.xls")
    shutil.copy2(summary, out)

    app = wc.Dispatch("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    try:
        wb = app.Workbooks.Open(str(out))
        ws = wb.Worksheets(1)
        rows = parse_summary_rows(ws)
        print(f"汇总表解析出 {len(rows)} 个单位工程")

        links = []
        for row_no, name, suffix in rows:
            src = find_tender_file(root, suffix)
            swb = app.Workbooks.Open(str(src), ReadOnly=False)
            sws = swb.Worksheets(1)
            sheet_name, last_row = sws.Name, sws.UsedRange.Row + sws.UsedRange.Rows.Count - 1
            before_n = wb.Worksheets.Count
            # 位置参数 Copy(Before, After)：命名参数 After= 会被 pywin32 静默忽略
            sws.Copy(None, wb.Worksheets(before_n))
            swb.Close(False)
            if wb.Worksheets.Count != before_n + 1:
                raise RuntimeError(f"sheet 复制静默失败：{src.name}")
            links.append((row_no, sheet_name, last_row))
            print(f"  + D{row_no:<3} {sheet_name:<12} ({last_row}行) <- {src.name}")

        for row_no, sheet_name, last_row in links:
            ws.Cells(row_no, 4).Formula = f"='{sheet_name}'!$Q${last_row}"

        wb.Save()
        wb.Close(False)
        print(f"\n保存: {out}")
    finally:
        app.Quit()


if __name__ == "__main__":
    main()
