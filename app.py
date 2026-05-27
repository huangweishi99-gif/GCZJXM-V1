#!/usr/bin/env python3
"""智能清单组价 — 命令行入口。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.database import init_database, reset_database
from src.export.excel import export_pricing_job
from src.knowledge.repository import KnowledgeRepository
from src.pricing.engine import PricingEngine


def _resolve_file(path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    for d in (ROOT / "清单数据资料", ROOT / "清单数据资料" / "AI学习清单"):
        alt = d / Path(path).name
        if not p.exists() and alt.exists():
            p = alt
            break
    if not p.exists():
        raise FileNotFoundError(f"找不到文件: {path}")
    return str(p)


def _engine(args) -> PricingEngine:
    mode = getattr(args, "match_mode", None)
    return PricingEngine(match_mode=mode)


def cmd_init(_: argparse.Namespace) -> None:
    print(f"数据库已初始化: {init_database()}")


def cmd_reset(_: argparse.Namespace) -> None:
    print(f"数据库已重建: {reset_database()}")


def cmd_relearn_all(args: argparse.Namespace) -> None:
    folder = ROOT / "清单数据资料" / "AI学习清单"
    skip = {"甲方一般表头", "表头"}
    files = sorted(
        p
        for p in folder.glob("*")
        if p.suffix.lower() in (".xlsx", ".xls")
        and not any(k in p.name for k in skip)
    )
    if not files:
        raise FileNotFoundError(f"未找到学习资料: {folder}")
    if args.reset:
        reset_database()
    else:
        init_database()
    repo = KnowledgeRepository()
    results = []
    for p in files:
        r = repo.learn_from_file(str(p))
        results.append(r)
        print(f"✓ {p.name}: 学习 {r['learned_records']} 条")
    print("\n库内统计:", json.dumps(repo.stats(), ensure_ascii=False))
    # 汇总导出
    _export_all_summary(results, files)


def _export_all_summary(results, files):
    from pathlib import Path
    import pandas as pd
    from src.ingest.parser import parse_workbook
    from src.normalize.feature_extract import extract_feature_profile

    rows = []
    for p in files:
        wb = parse_workbook(p)
        for l in wb.lines:
            if not l.cost_unit_price and not l.has_cost_detail:
                continue
            prof = extract_feature_profile(l.feature, l.name)
            qty = l.quantity or 0
            cu = l.cost_unit_price or 0
            rows.append(
                {
                    "来源文件": p.name,
                    "工程": wb.project_name[:50],
                    "名称": l.name,
                    "做法摘要": prof.summary(),
                    "单位": l.unit,
                    "工程量": qty,
                    "成本单价": cu,
                    "成本合价": round(cu * qty, 2),
                    "主材": l.material_main,
                    "人工": l.labor,
                    "辅材": l.material_aux,
                }
            )
    if not rows:
        return
    out = Path("data/exports/全部项目成本库汇总.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        pd.DataFrame(results).to_excel(w, sheet_name="导入结果", index=False)
        df.to_excel(w, sheet_name="成本明细", index=False)
        df.groupby("来源文件", as_index=False).agg(
            项数=("名称", "count"), 成本合价=("成本合价", "sum")
        ).to_excel(w, sheet_name="按项目汇总", index=False)
    print(f"汇总已导出: {out}")


def cmd_learn(args: argparse.Namespace) -> None:
    repo = KnowledgeRepository()
    result = repo.learn_from_file(_resolve_file(args.file), project_name=args.name)
    print("已分析并记入知识库：")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    st = repo.stats()
    print(f"库内: 项目{st['projects']} | 标准项{st['standard_items']} | 成本记录{st['cost_records']}")


def cmd_tender(args: argparse.Namespace) -> None:
    repo = KnowledgeRepository()
    result = repo.import_tender(_resolve_file(args.file), project_name=args.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.price:
        pr = _engine(args).run_for_project(result["project_id"])
        print("组价:", json.dumps(pr, ensure_ascii=False, indent=2))
        if args.export:
            print(
                f"已导出: {export_pricing_job(pr['job_id'], use_dedupe_link=args.dedupe_link)}"
            )


def cmd_price(args: argparse.Namespace) -> None:
    pr = _engine(args).run_for_project(args.project)
    print(json.dumps(pr, ensure_ascii=False, indent=2))
    if args.export:
        print(
            f"已导出: {export_pricing_job(pr['job_id'], output_path=args.output, use_dedupe_link=args.dedupe_link)}"
        )


def cmd_export(args: argparse.Namespace) -> None:
    print(
        f"已导出: {export_pricing_job(args.job, output_path=args.output, use_dedupe_link=args.dedupe_link)}"
    )


def cmd_match(args: argparse.Namespace) -> None:
    rows = _engine(args).search(args.name, args.feature or "", args.unit, top_n=args.top)
    print(f"匹配模式: {args.match_mode or 'auto'}\n")
    if not rows:
        print("无匹配结果（请检查单位是否与库内一致）")
        return
    for i, r in enumerate(rows, 1):
        print(
            f"{i}. [{r['match_type']}/{r['level']}] {r['name']} | {r['unit']} "
            f"名称{r['name_score']:.0%} 特征{r['feature_score']:.0%} "
            f"综合{r['total_score']:.0%} (样本{r['samples']})"
        )
        if r["feature"]:
            print(f"   特征: {r['feature']}…")


def cmd_dedupe(args: argparse.Namespace) -> None:
    from src.link.export_link import export_dedupe_workbook

    path = _resolve_file(args.file)
    out, items = export_dedupe_workbook(path, output_path=args.output)
    total = sum(i.line_count for i in items)
    saved = total - len(items)
    pct = round(100 * saved / total, 1) if total else 0
    print(f"去重: {total} 行 → {len(items)} 项（少填 {saved} 行，约 {pct}%）")
    print(f"已导出: {out}")


def cmd_link_price(args: argparse.Namespace) -> None:
    from src.link.export_link import export_linked_pricing

    tender = _resolve_file(args.tender)
    master = _resolve_file(args.master)
    out = export_linked_pricing(tender, master, output_path=args.output)
    print(f"链接组价表已导出: {out}")


def cmd_backfill(_: argparse.Namespace) -> None:
    from src.knowledge.backfill import backfill_method_signatures

    init_database()
    r = backfill_method_signatures()
    print(f"已回填做法标签: {r['updated']} 条标准项")


def cmd_stats(_: argparse.Namespace) -> None:
    repo = KnowledgeRepository()
    print(json.dumps(repo.stats(), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="智能清单组价系统")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_match_mode(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--match-mode",
            choices=["exact", "fuzzy", "auto"],
            default=None,
            help="精确/模糊/自动匹配（默认读 config/settings.json）",
        )

    sub.add_parser("init").set_defaults(func=cmd_init)

    p_reset = sub.add_parser("reset", help="清空并重建数据库")
    p_reset.set_defaults(func=cmd_reset)

    p_all = sub.add_parser("relearn-all", help="批量学习 AI学习清单 下全部项目")
    p_all.add_argument("--reset", action="store_true", help="先清空数据库再导入")
    p_all.set_defaults(func=cmd_relearn_all)

    p_learn = sub.add_parser("learn", help="新清单+价格 → 知识库")
    p_learn.add_argument("file")
    p_learn.add_argument("--name", default=None)
    p_learn.set_defaults(func=cmd_learn)

    p_tender = sub.add_parser("tender", help="导入招标清单")
    p_tender.add_argument("file")
    p_tender.add_argument("--name", default=None)
    p_tender.add_argument("--price", action="store_true")
    p_tender.add_argument("--export", action="store_true")
    p_tender.add_argument(
        "--dedupe-link",
        action="store_true",
        help="导出含去重母表+公式链接（相同项只填母表一次）",
    )
    add_match_mode(p_tender)
    p_tender.set_defaults(func=cmd_tender)

    p_price = sub.add_parser("price", help="组价")
    p_price.add_argument("--project", type=int, required=True)
    p_price.add_argument("--export", action="store_true")
    p_price.add_argument("--output", default=None)
    p_price.add_argument("--dedupe-link", action="store_true")
    add_match_mode(p_price)
    p_price.set_defaults(func=cmd_price)

    p_exp = sub.add_parser("export")
    p_exp.add_argument("--job", type=int, required=True)
    p_exp.add_argument("--output", default=None)
    p_exp.add_argument("--dedupe-link", action="store_true")
    p_exp.set_defaults(func=cmd_export)

    p_match = sub.add_parser("match", help="测试相同项匹配（精确/模糊）")
    p_match.add_argument("name", help="项目名称")
    p_match.add_argument("--feature", default="", help="项目特征")
    p_match.add_argument("--unit", required=True, help="单位")
    p_match.add_argument("--top", type=int, default=5)
    add_match_mode(p_match)
    p_match.set_defaults(func=cmd_match)

    p_ded = sub.add_parser("dedupe", help="去重清单（名称+单位+做法），导出母表")
    p_ded.add_argument("file")
    p_ded.add_argument("--output", default=None)
    p_ded.set_defaults(func=cmd_dedupe)

    p_link = sub.add_parser("link-price", help="招标清单链接去重母表单价（Excel公式）")
    p_link.add_argument("tender", help="全量招标清单")
    p_link.add_argument("--master", required=True, help="去重母表 xlsx")
    p_link.add_argument("--output", default=None)
    p_link.set_defaults(func=cmd_link_price)

    sub.add_parser("backfill", help="为知识库回填做法标签（特征解析）").set_defaults(
        func=cmd_backfill
    )

    sub.add_parser("stats").set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
