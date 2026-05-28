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
        r = repo.learn_from_file(str(p), export_anatomy=True)
        r["source_file"] = str(p)
        results.append(r)
        if r.get("anatomy_report"):
            print(f"  解剖报告: {r['anatomy_report']}")
        print(f"✓ {p.name}: 学习 {r['learned_records']} 条")
    print("\n库内统计:", json.dumps(repo.stats(), ensure_ascii=False))
    # 汇总导出
    _export_all_summary(results, files)


def _export_all_summary(results, files):
    from pathlib import Path

    import pandas as pd

    from src.db.database import get_connection

    out = Path("data/exports/全部项目成本库汇总.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)

    import_rows = []
    for r in results:
        anat = r.get("anatomy") or {}
        import_rows.append(
            {
                "来源文件": Path(r.get("source_file", "")).name
                if r.get("source_file")
                else "",
                "工程名称": r.get("project_name"),
                "城市": r.get("city") or "通用",
                "档位": r.get("price_tier", "mid"),
                "范围": r.get("scope", ""),
                "清单行": r.get("total_lines"),
                "入库成本行": r.get("learned_records"),
                "跳过无成本": r.get("skipped_no_cost"),
                "标准项贡献": anat.get("standard_items_contributed"),
                "解剖报告": r.get("anatomy_report", ""),
            }
        )
    df_import = pd.DataFrame(import_rows)

    conn = get_connection()
    try:
        df_detail = pd.read_sql_query(
            """SELECT lpf.city AS 城市, lpf.price_tier AS 档位,
                      si.name_norm AS 项目名称, si.method_summary AS 做法摘要,
                      si.unit_norm AS 单位,
                      lpf.material_main AS 主材, lpf.material_aux AS 辅材,
                      lpf.labor AS 人工, lpf.machinery AS 机械,
                      lpf.cost_unit_price AS 成本单价, lpf.sample_count AS 样本数
               FROM line_price_facts lpf
               JOIN standard_items si ON si.id = lpf.standard_item_id
               ORDER BY lpf.city, lpf.price_tier, si.name_norm
               LIMIT 8000""",
            conn,
        )
        df_mat = pd.read_sql_query(
            """SELECT city AS 城市, price_tier AS 档位, material_key AS 材料键,
                      spec_text AS 规格, unit_norm AS 单位,
                      material_main AS 主材单价, sample_count AS 样本数
               FROM material_price_facts
               ORDER BY city, price_tier, material_key""",
            conn,
        )
        df_proj = pd.read_sql_query(
            """SELECT name AS 工程, city AS 城市, price_tier AS 档位,
                      project_type AS 类型, source_file AS 来源
               FROM projects WHERE project_type='historical'
               ORDER BY id""",
            conn,
        )
    finally:
        conn.close()

    with pd.ExcelWriter(out, engine="openpyxl") as w:
        df_import.to_excel(w, sheet_name="01_项目导入归类", index=False)
        df_proj.to_excel(w, sheet_name="02_知识库项目索引", index=False)
        if not df_detail.empty:
            df_detail.to_excel(w, sheet_name="03_清单项价库", index=False)
        if not df_mat.empty:
            df_mat.to_excel(w, sheet_name="04_材料价库", index=False)
        pd.DataFrame(
            [
                {"说明": "本表由 relearn-all 自动生成"},
                {"说明": "每项目解剖报告见 data/exports/解剖报告/"},
                {"说明": "组价时按 城市+档位+名称特征相似 参照"},
            ]
        ).to_excel(w, sheet_name="说明", index=False)
    print(f"汇总已导出: {out}")


def _add_region_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--city", default=None, help="城市，如 深圳（不填则从文件名推断）")
    p.add_argument(
        "--tier",
        default=None,
        choices=["high", "mid", "low", "高", "中", "低"],
        help="价格档位：high/mid/low",
    )


def cmd_learn(args: argparse.Namespace) -> None:
    repo = KnowledgeRepository()
    result = repo.learn_from_file(
        _resolve_file(args.file),
        project_name=args.name,
        city=args.city,
        price_tier=args.tier,
        export_anatomy=not getattr(args, "no_anatomy", False),
    )
    print("已分析并记入知识库（含解剖）：")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("anatomy_report"):
        print(f"解剖报告: {result['anatomy_report']}")
    st = repo.stats()
    print(json.dumps(st, ensure_ascii=False, indent=2))


def cmd_tender(args: argparse.Namespace) -> None:
    repo = KnowledgeRepository()
    result = repo.import_tender(
        _resolve_file(args.file),
        project_name=args.name,
        city=args.city,
        price_tier=args.tier,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.price:
        pr = _engine(args).run_for_project(result["project_id"])
        print("组价:", json.dumps(pr, ensure_ascii=False, indent=2))
        if args.export:
            from src.export.inplace_bidder import fill_tender_inplace

            out = fill_tender_inplace(
                _resolve_file(args.file),
                pr["job_id"],
                output_path=args.output,
                reference_fill=not args.no_reference_fill,
            )
            print(f"已导出（原表组价+链接）: {out}")
            if args.dedupe_link:
                from src.export.excel import export_pricing_job

                print(
                    f"另存模板表: {export_pricing_job(pr['job_id'], use_dedupe_link=True)}"
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


def cmd_backfill_kb(_: argparse.Namespace) -> None:
    from src.knowledge.backfill_kb import backfill_projects_and_facts

    init_database()
    repo = KnowledgeRepository()
    conn = repo.conn()
    try:
        r = backfill_projects_and_facts(conn)
        conn.commit()
    finally:
        conn.close()
    print("知识库价库已重建：", json.dumps(r, ensure_ascii=False, indent=2))
    print(json.dumps(repo.stats(), ensure_ascii=False, indent=2))


def cmd_import_catalog(args: argparse.Namespace) -> None:
    from src.knowledge.material_catalog import import_material_catalog_xlsx

    init_database()
    fp = _resolve_file(args.file)
    r = import_material_catalog_xlsx(fp)
    print(
        f"材料目录已导入: {r['imported']} 条 (主材 {r['main_count']}, 辅材 {r['aux_count']}, 库内合计 {r['catalog_total']})"
    )
    print(f"来源: {r['source']}")


def cmd_audit_judge(args: argparse.Namespace) -> None:
    from src.pricing.judge_audit import run_judge_audit

    init_database()
    out = Path(args.output) if args.output else ROOT / "data" / "exports" / "抽检报告_人材机判断.xlsx"
    if args.no_export:
        out = None
    summary = run_judge_audit(
        exclude_self=not args.include_self,
        rel_tol=args.rel_tol,
        abs_tol=args.abs_tol,
        total_rel_tol=args.total_tol,
        limit=args.limit,
        project_id=args.project,
        export_path=out,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if out:
        print(f"\n明细已导出: {out}")


def cmd_judge(args: argparse.Namespace) -> None:
    from src.knowledge.query import PricingContext
    from src.pricing.component_judge import judge_line_components
    from src.pricing.engine import PricingEngine

    init_database()
    repo = KnowledgeRepository()
    engine = PricingEngine()
    tier = args.tier or "mid"
    if tier in ("高", "中", "低"):
        tier = {"高": "high", "中": "mid", "低": "low"}[tier]
    ctx = PricingContext(city=args.city or "", price_tier=tier) if (args.city or args.tier) else None
    j = judge_line_components(
        args.name,
        args.feature or "",
        args.unit,
        engine,
        repo,
        ctx=ctx if args.city or args.tier else None,
    )
    out = {
        "工艺": j.craft_label,
        "专业": j.trade,
        "置信度": round(j.confidence, 3),
        "可自动填入": j.auto_fill_ok,
        "来源": j.source,
        "主材": j.material_main,
        "辅材": j.material_aux,
        "人工": j.labor,
        "机械": j.machinery,
        "分项置信": j.field_confidence,
        "说明": j.notes,
        "预警": j.warnings,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


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

    p_learn = sub.add_parser("learn", help="新清单+价格 → 知识库（自动解剖）")
    p_learn.add_argument("file")
    p_learn.add_argument("--name", default=None)
    p_learn.add_argument("--no-anatomy", action="store_true", help="不导出解剖报告 Excel")
    _add_region_args(p_learn)
    p_learn.set_defaults(func=cmd_learn)

    p_tender = sub.add_parser("tender", help="导入招标清单")
    p_tender.add_argument("file")
    p_tender.add_argument("--name", default=None)
    _add_region_args(p_tender)
    p_tender.add_argument("--price", action="store_true")
    p_tender.add_argument("--export", action="store_true")
    p_tender.add_argument(
        "--no-reference-fill",
        action="store_true",
        help="未达 A/B 级时不填历史参考价（默认会填 Top1 参考并标注需确认）",
    )
    p_tender.add_argument("--output", default=None, help="导出路径（默认 data/exports/原名_组价.xlsx）")
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

    sub.add_parser(
        "backfill-kb",
        help="回填城市/档位并重建 line_price_facts、material_price_facts",
    ).set_defaults(func=cmd_backfill_kb)

    sub.add_parser("stats").set_defaults(func=cmd_stats)

    p_cat = sub.add_parser(
        "import-catalog",
        help="导入主材辅材判定.xlsx 到 material_catalog",
    )
    p_cat.add_argument(
        "file",
        nargs="?",
        default="清单数据资料/AI学习清单/主材辅材判定.xlsx",
        help="判定表路径（默认 AI学习清单/主材辅材判定.xlsx）",
    )
    p_cat.set_defaults(func=cmd_import_catalog)

    p_judge = sub.add_parser("judge", help="判断单项人材机（多源融合+置信度）")
    p_judge.add_argument("name", help="项目名称")
    p_judge.add_argument("--feature", default="", help="项目特征")
    p_judge.add_argument("--unit", required=True, help="单位")
    _add_region_args(p_judge)
    p_judge.set_defaults(func=cmd_judge)

    p_audit = sub.add_parser(
        "audit-judge",
        help="批量回测人材机判断准确率（对比历史成本拆解）",
    )
    p_audit.add_argument("--no-export", action="store_true", help="不导出 Excel")
    p_audit.add_argument("--output", default=None, help="导出路径（默认 data/exports/抽检报告_人材机判断.xlsx）")
    p_audit.add_argument("--limit", type=int, default=None, help="最多抽检条数（不填=全量）")
    p_audit.add_argument("--project", type=int, default=None, help="仅抽检指定 project_id")
    p_audit.add_argument(
        "--include-self",
        action="store_true",
        help="不排除同标准项（会高估整项匹配准确率，仅对比用）",
    )
    p_audit.add_argument("--rel-tol", type=float, default=0.20, help="分项相对误差容忍（默认20%%）")
    p_audit.add_argument("--abs-tol", type=float, default=5.0, help="分项绝对误差容忍/元（实际≈0时）")
    p_audit.add_argument("--total-tol", type=float, default=0.15, help="合计相对误差容忍（默认15%%）")
    p_audit.set_defaults(func=cmd_audit_judge)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
