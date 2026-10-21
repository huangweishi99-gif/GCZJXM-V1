"""pricing_pipeline.py — 智能组价标准流程编排器（六阶段，断点续跑）。
阶段1-3 全自动（体检→组价导出+母行链接→格式整理），阶段4-5 生成工作单/复核记录模板由 AI+用户执行，
阶段6 由 finalize-absorb 技能收口。状态落盘 data/pipeline/<slug>/state.json。
用法:
  python pricing_pipeline.py run "<招标清单>" --city 深圳 --tier mid [--from N] [--dry-run]
  python pricing_pipeline.py status "<招标清单>"
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boq_rows import read_openpyxl  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
PIPE = ROOT / "data" / "pipeline"
SKILL = Path(__file__).resolve().parents[1]

STAGES = [
    (1, "清单体检", "app.py validate-boq"),
    (2, "组价导出+母行链接", "app.py tender --price --export --dedupe-link"),
    (3, "格式整理(COM)", "qingdan apply_standard_format.py"),
    (4, "工艺组价", "AI 按 craft-pricing 八步法填 03_组价工作单.csv"),
    (5, "复核", "AI+用户填 05_复核记录.csv（强制产物）"),
    (6, "交付+定稿吸收", "切 finalize-absorb: absorb_final.py"),
]

WORK_ORDER_COLS = ["序号", "分部工程", "清单项名称", "项目特征", "单位", "工程量",
                   "系统填价_成本单价", "AI组价_主材", "AI组价_损耗率", "AI组价_人工",
                   "AI组价_辅材", "AI组价_机械",
                   "价源(定稿/期刊/定额/历史/市场参考/网查)", "工序拆解要点", "备注"]
PENDING_COLS = ["序号", "清单项名称", "缺漏参数", "特征原文", "影响", "建议确认对象"]
REVIEW_COLS = ["序号", "分部工程", "清单项名称", "项目特征", "单位", "工程量",
               "AI原值_成本单价", "复核值", "差异", "差异金额=(复核值-原值)*工程量",
               "复核依据(价源+出处)", "复核人", "复核日期", "备注"]


def write_templates(wd: Path, items: list):
    """预填三张 CSV（已存在则不覆盖）；items 来自导出文件的清单行"""
    wo = wd / "03_组价工作单.csv"
    if not wo.exists():
        with wo.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(WORK_ORDER_COLS)
            for i, it in enumerate(items, 1):
                w.writerow([i, it["sheet"], it["name"], it["feature"], it["unit"],
                            it["qty"], it["cost"], "", "", "", "", "", "", "", ""])
    pj = wd / "04_待确认清单.csv"
    if not pj.exists():
        with pj.open("w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(PENDING_COLS)
    rv = wd / "05_复核记录.csv"
    if not rv.exists():
        with rv.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(REVIEW_COLS)
            for i, it in enumerate(items, 1):
                w.writerow([i, it["sheet"], it["name"], it["feature"], it["unit"],
                            it["qty"], it["cost"], "", "", "", "", "", "", ""])


def slugify(fp: Path) -> str:
    s = re.sub(r"[\\/:：*?\"<>|\s]+", "_", fp.stem)[:60].strip("_")
    return s or "project"


def workdir(fp: Path) -> Path:
    return PIPE / slugify(fp)


def load_state(fp: Path) -> dict:
    sp = workdir(fp) / "state.json"
    if sp.exists():
        return json.loads(sp.read_text(encoding="utf-8"))
    return {"file": str(fp), "city": "", "tier": "mid",
            "stages": {str(n): {"status": "pending"} for n, _, _ in STAGES}}


def save_state(fp: Path, st: dict):
    workdir(fp).mkdir(parents=True, exist_ok=True)
    (workdir(fp) / "state.json").write_text(
        json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def run_cli(args, timeout=1800):
    r = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "app.py"), *args],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0:
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        raise SystemExit(f"app.py {' '.join(args)} 失败 exit={r.returncode}")
    return r.stdout


def cmd_status(args):
    fp = Path(args.file).resolve()
    st = load_state(fp)
    print(f"流程目录: {workdir(fp)}")
    for n, name, how in STAGES:
        s = st["stages"].get(str(n), {})
        mark = {"done": "✅", "pending": "⬜", "active": "🔵"}.get(s.get("status"), "⬜")
        art = f"  → {s['artifact']}" if s.get("artifact") else ""
        print(f" {mark} 阶段{n} {name}{art}")
        print(f"      {how}")


def cmd_run(args):
    fp = Path(args.file).resolve()
    if not fp.exists():
        raise SystemExit(f"文件不存在: {fp}")
    wd = workdir(fp)
    st = load_state(fp)
    st["city"] = args.city
    st["tier"] = args.tier

    def done(n, artifact=""):
        st["stages"][str(n)] = {"status": "done", "artifact": artifact}
        if not args.dry_run:
            save_state(fp, st)

    print(f"流程目录: {wd}\n清单: {fp.name}  城市: {args.city}  档位: {args.tier}"
          + ("  [dry-run]" if args.dry_run else ""))

    # 阶段1 体检
    if args.from_stage <= 1:
        print("\n[阶段1] 清单五要素体检 ...")
        if not args.dry_run:
            out = run_cli(["validate-boq", str(fp)])
            (wd / "01_体检报告.txt").write_text(out, encoding="utf-8")
            done(1, "01_体检报告.txt")
            print("      → 01_体检报告.txt（有问题项先让用户补齐再往下）")
    # 阶段2 组价导出+母行链接
    if args.from_stage <= 2:
        print("[阶段2] tender 组价导出 + 去重母行链接 ...")
        if not args.dry_run:
            run_cli(["tender", str(fp), "--city", args.city, "--tier", args.tier,
                     "--price", "--export", "--dedupe-link",
                     "--output", str(wd / "02_成本分析_去重链接.xlsx")])
            done(2, "02_成本分析_去重链接.xlsx")
    # 阶段3 格式整理
    if args.from_stage <= 3:
        print("[阶段3] 套用标准打印格式（Excel COM 保真）...")
        if not args.dry_run:
            fmt = SKILL.parent / "qingdan-format-standard" / "scripts" / "apply_standard_format.py"
            if fmt.exists():
                r = subprocess.run([sys.executable, "-X", "utf8", str(fmt),
                                    str(wd / "02_成本分析_去重链接.xlsx")],
                                   cwd=ROOT, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=600)
                print(r.stdout.strip() or r.stderr.strip()[:500])
            else:
                print("      (apply_standard_format.py 未找到，手动跑 qingdan-format-standard)")
            done(3)
    # 阶段4/5 模板（自动从导出抄行预填）
    if args.from_stage <= 4:
        print("[阶段4/5] 生成组价工作单 + 待确认清单 + 复核记录 ...")
        if not args.dry_run:
            export = wd / "02_成本分析_去重链接.xlsx"
            items = []
            if export.exists():
                try:
                    items = read_openpyxl(export)
                except Exception as e:
                    print(f"      (导出读取失败 {e}，退化为空模板)")
            write_templates(wd, items)
            print(f"      预填清单行 {len(items)} 条（工作单/复核记录）")
            done(4, "03_组价工作单.csv / 04_待确认清单.csv")
    if not args.dry_run:
        save_state(fp, st)
    print(f"""
== 自动阶段完成，接下来 ==
  阶段4: 按 craft-pricing 八步法逐行组价，写入 {wd / '03_组价工作单.csv'}
         （先 craft_db.py query 查工艺链；网查价不进库）
  阶段5: 复核改动写入 {wd / '05_复核记录.csv'}（强制产物，改值必须填依据）
  阶段6: 用户说"定稿" → finalize-absorb 吸收
查看进度: python {Path(__file__).name} status "{fp}"
""")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("file")
    r.add_argument("--city", required=True)
    r.add_argument("--tier", default="mid")
    r.add_argument("--from", dest="from_stage", type=int, default=1)
    r.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("file")
    args = p.parse_args()
    if args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "status":
        cmd_status(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
