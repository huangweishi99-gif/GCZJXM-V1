"""apply_workorder.py — 把 03_组价工作单.csv 的 AI 组价人材机 COM 保真回写到交付 xlsx。
铁律:
  - 只写母行/独立行；目标单元格现有公式（= 开头）一律跳过（链接子行 L:P 是公式，覆盖=毁链接）;
  - 匹配键 = (分部工程=sheet名, 名称, 单位)，同名多行再比特征；写 L主材/M损耗/N人工/O辅材/P机械；
  - K 列是公式自动重算，不要写 K。
用法:
  python apply_workorder.py "data/pipeline/<项目目录>" [--dry-run]
  python apply_workorder.py "<交付xlsx路径>" [--dry-run]   # 工作单默认取同目录 03_组价工作单.csv
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boq_rows import norm, read_com  # noqa: E402

COMPONENT_COLS = [("AI组价_主材", "L"), ("AI组价_损耗率", "M"), ("AI组价_人工", "N"),
                  ("AI组价_辅材", "O"), ("AI组价_机械", "P")]


def to_num(s):
    s = (s or "").strip().rstrip("%")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("target", help="流程目录 或 交付 xlsx")
    p.add_argument("--workorder", default=None, help="工作单 CSV 路径（默认按目标推导）")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    t = Path(a.target).resolve()
    if t.is_dir():
        export, wo = t / "02_成本分析_去重链接.xlsx", t / "03_组价工作单.csv"
    else:
        export, wo = t, t.parent / "03_组价工作单.csv"
    if a.workorder:
        wo = Path(a.workorder).resolve()
    if not export.exists():
        raise SystemExit(f"交付文件不存在: {export}")
    if not wo.exists():
        raise SystemExit(f"工作单不存在: {wo}")
    rows = [r for r in csv.DictReader(wo.open(encoding="utf-8-sig"))
            if any((r.get(c) or "").strip() for c, _ in COMPONENT_COLS)]
    if not rows:
        raise SystemExit("工作单里没有已填人材机的行")
    print(f"待回写 {len(rows)} 行 → {export.name}")

    items = read_com(export)
    index = {}
    for it in items:
        index.setdefault((it["sheet"], norm(it["name"]), norm(it["unit"])), []).append(it)

    import win32com.client
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    wb = excel.Workbooks.Open(str(export))
    written, skipped_link, no_match = 0, 0, []
    try:
        for r in rows:
            key = (r.get("分部工程", ""), norm(r.get("清单项名称")), norm(r.get("单位")))
            cands = index.get(key)
            if not cands:
                no_match.append(r.get("清单项名称", "?"))
                continue
            it = cands[0]
            if len(cands) > 1:
                f = norm(r.get("项目特征"))
                same = [c for c in cands if norm(c["feature"]) == f]
                it = same[0] if same else cands[0]
                print(f"  [同名{len(cands)}行] {r.get('清单项名称')} → "
                      f"{'特征匹配' if same else '取首行，请人工确认'}")
            ws = wb.Worksheets(it["sheet"])
            for col_name, xcol in COMPONENT_COLS:
                v = to_num(r.get(col_name))
                if v is None:
                    continue
                cell = ws.Range(f"{xcol}{it['xl_row']}")
                # 注意: 必须用 .Formula 判链接——.Value 返回的是公式缓存计算值
                if isinstance(cell.Formula, str) and cell.Formula.startswith("="):
                    skipped_link += 1
                    continue
                if a.dry_run:
                    print(f"  [dry] {it['sheet']}!{xcol}{it['xl_row']} <- {col_name}={v:g}")
                    continue
                cell.Value = v
                written += 1
        if not a.dry_run:
            wb.Save()
    finally:
        wb.Close(False)
        excel.Quit()
    print(f"完成: 写入 {written} 格, 跳过链接公式 {skipped_link} 格, 未匹配 {len(no_match)} 行")
    for nm in no_match[:20]:
        print(f"  未匹配: {nm}")


if __name__ == "__main__":
    main()
