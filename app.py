#!/usr/bin/env python3
"""智能清单组价 — 命令行入口。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

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
    for d in (
        ROOT / "清单数据资料",
        ROOT / "清单数据资料" / "AI学习清单",
        ROOT / "清单数据资料" / "甲方招标清单",
        ROOT / "data" / "exports",
    ):
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
        print(f"OK {p.name}: 学习 {r['learned_records']} 条")
    print("\n库内统计:", json.dumps(repo.stats(), ensure_ascii=False))
    # 汇总导出
    _export_all_summary(results, files)
    if getattr(args, "audit", False):
        _run_post_relearn_audit()


def _run_post_relearn_audit() -> None:
    from src.pricing.judge_audit import run_judge_audit

    print("\n=== audit-judge（learn 后回测）===")
    out_xlsx = ROOT / "data" / "exports" / "抽检报告_人材机判断.xlsx"
    out_json = ROOT / "data" / "exports" / "audit_judge_summary.json"
    summary = run_judge_audit(export_path=out_xlsx)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n明细: {out_xlsx}")
    print(f"摘要: {out_json}")


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


def cmd_link_inline(args: argparse.Namespace) -> None:
    """内嵌人工/主材/辅材机械列：引用历史价 + 组价 + 同表母行链接。"""
    from src.export.inline_cost_link import fill_inline_cost_link
    from src.knowledge.calibration import get_pair

    init_database()
    pair = get_pair(args.project) if args.project else None
    tender = _resolve_file(
        args.tender or (pair and pair.get("tender")) or ""
    )
    if not tender:
        raise SystemExit("请指定 --tender 或在 project_pairs 配置 tender")
    refs = [_resolve_file(p) for p in (args.reference or [])]
    if not refs and pair:
        refs = [_resolve_file(p) for p in pair.get("reference_tenders") or []]
    sheets = args.sheets or (pair.get("inline_sheets") if pair else None)
    if sheets and isinstance(sheets, str):
        sheets = [s.strip() for s in sheets.split(",") if s.strip()]
    tier = args.tier or (pair.get("tier") if pair else None) or "mid"
    if tier in ("高", "中", "低"):
        tier = {"高": "high", "中": "mid", "低": "low"}[tier]
    city = args.city or (pair.get("city") if pair else None) or "珠海"
    materials_ref = args.materials_ref or (
        pair.get("project_materials_ref") if pair else None
    ) or "haide_sales_office"
    out = args.output or (pair.get("export") if pair else None)
    report = fill_inline_cost_link(
        tender,
        refs,
        sheet_names=sheets,
        output_path=out,
        city=city,
        tier=tier,
        project_materials_ref=materials_ref,
    )
    print(
        json.dumps(
            {
                "输出": report.output_path,
                "母行": report.masters,
                "链接行": report.slaves,
                "跨表链接": report.cross_sheet_slaves,
                "引用命中": report.reference_hits,
                "系统组价": report.judged,
                "分表": report.sheets,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


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


def cmd_backfill_cost_splits(_: argparse.Namespace) -> None:
    from src.knowledge.backfill_cost_splits import backfill_cost_component_splits

    init_database()
    repo = KnowledgeRepository()
    conn = repo.conn()
    try:
        r = backfill_cost_component_splits(conn)
        conn.commit()
    finally:
        conn.close()
    print("整价分项回填完成：", json.dumps(r, ensure_ascii=False, indent=2))
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


def cmd_import_project_materials(args: argparse.Namespace) -> None:
    from src.knowledge.project_materials import import_project_materials_xlsx

    init_database()
    fp = _resolve_file(args.file)
    ref = args.ref or args.project.replace(" ", "_")[:48]
    r = import_project_materials_xlsx(
        fp,
        project_name=args.project,
        project_ref=ref,
        city=args.city or "",
        price_tier=args.tier,
    )
    print(json.dumps(r, ensure_ascii=False, indent=2))


def cmd_import_quota(args: argparse.Namespace) -> None:
    """导入广联达定额标准库（JSON格式）。"""
    from src.knowledge.quota_manager import QuotaManager

    init_database()
    fp = _resolve_file(args.file) if args.file else str(ROOT / "config" / "quota_standards.json")
    mgr = QuotaManager()
    r = mgr.import_from_json(fp)
    print(json.dumps(r, ensure_ascii=False, indent=2))


def cmd_quota_match(args: argparse.Namespace) -> None:
    """测试定额匹配（根据项目名称和特征匹配定额子目）。"""
    from src.knowledge.quota_manager import QuotaManager
    from src.pricing.feature_to_quota import FeatureToQuotaMatcher

    init_database()
    mgr = QuotaManager()
    matcher = FeatureToQuotaMatcher(mgr)
    results = matcher.match_by_feature(args.name, args.feature or "", args.unit, top_n=args.top)
    for res in results:
        print(json.dumps(res, ensure_ascii=False, indent=2))


def cmd_quota_cost(args: argparse.Namespace) -> None:
    """计算定额子目成本。"""
    from src.knowledge.quota_manager import QuotaManager

    init_database()
    mgr = QuotaManager()
    cost = mgr.calculate_cost(args.code, target_unit=args.unit, city=getattr(args, "city", "") or "")
    if cost:
        print(json.dumps(cost, ensure_ascii=False, indent=2))
    else:
        print(f"未找到定额子目: {args.code}")


def cmd_audit_price(args: argparse.Namespace) -> None:
    """价格数量级审计：扫描市场参考价/定额价/人工机械单价中的越界项。"""
    from src.pricing.sanity_check import run_full_audit

    report = run_full_audit()
    total = report["total_issues"]
    print(f"价格审计完成，共发现 {total} 处数量级越界：\n")
    for source, issues in report.items():
        if source == "total_issues":
            continue
        label = {
            "market_reference": "市场参考价",
            "quota_standards": "定额内嵌材料价",
            "labor_rates": "人工/机械单价",
        }.get(source, source)
        print(f"--- {label} ({len(issues)}) ---")
        for x in issues[:30]:
            print(f"  {x.get('name')} {x.get('price')}: {x.get('issue')}")
        if len(issues) > 30:
            print(f"  ... 其余 {len(issues) - 30} 条省略")
        print()
    if total == 0:
        print("全部通过，无越界。")
    else:
        print("提示：越界项会触发 [价格校验] 标注并降级 auto_fill，需人工复核。")


def cmd_quote_fees(args: argparse.Namespace) -> None:
    """取费建议：成本单价 → 综合单价（管理费+利润+风险）及单位工程费汇总。"""
    from src.pricing.fee_rates import build_summary, get_rates

    rates = get_rates(args.category, args.tier, style=args.style)
    style_tag = f"·{args.style}" if args.style else ""
    print(f"取费标准（{args.category or '通用'}·{args.tier}{style_tag}）：")
    print(json.dumps(rates, ensure_ascii=False, indent=2))
    if args.cost:
        s = build_summary(args.cost, args.quantity or 1, args.category, args.tier, style=args.style)
        print("\n费用汇总：")
        print(json.dumps(s, ensure_ascii=False, indent=2))


def cmd_validate_boq(args: argparse.Namespace) -> None:
    """招标清单可投标性体检：五要素（编码/名称/特征/单位/工程量）+ 废标雷区。"""
    from src.export.boq_validation import format_report, validate_boq

    fp = _resolve_file(args.file)
    print(f"正在解析 {fp} ...")
    report = validate_boq(str(fp))
    print(format_report(report))


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
        exclude_simulated=not getattr(args, "include_simulated", False),
        exclude_fee_items=not getattr(args, "include_fee", False),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if out:
        print(f"\n明细已导出: {out}")
    json_path = ROOT / "data" / "exports" / "audit_judge_summary.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"摘要已写入: {json_path}")


def cmd_audit_review(args: argparse.Namespace) -> None:
    from src.pricing.audit_review import build_audit_review
    from src.pricing.judge_audit import run_judge_audit

    init_database()
    input_path = Path(args.input) if args.input else ROOT / "data" / "exports" / "抽检报告_人材机判断.xlsx"
    if args.refresh or not input_path.exists():
        summary = run_judge_audit(
            exclude_self=not args.include_self,
            exclude_simulated=not getattr(args, "include_simulated", False),
            exclude_fee_items=not getattr(args, "include_fee", False),
            limit=args.limit,
            export_path=input_path,
        )
        summary_path = ROOT / "data" / "exports" / "audit_judge_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已刷新抽检报告: {input_path}")
    output_path = Path(args.output) if args.output else ROOT / "data" / "exports" / "待确认清单_人材机判断.xlsx"
    json_path = Path(args.json_output) if args.json_output else ROOT / "data" / "exports" / "audit_review_summary.json"
    review = build_audit_review(
        input_path,
        output_path=output_path,
        json_path=json_path,
        top=args.top,
    )
    print(json.dumps(review, ensure_ascii=False, indent=2))
    print(f"\n待确认清单已导出: {output_path}")
    print(f"摘要已写入: {json_path}")


def cmd_judge(args: argparse.Namespace) -> None:
    from src.knowledge.query import PricingContext
    from src.pricing.component_judge import (
        judge_line_components,
        judgment_explanation,
        judgment_risk_tags,
    )
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
        "解释摘要": judgment_explanation(j),
        "风险标签": judgment_risk_tags(j, name=args.name, feature=args.feature or ""),
        "说明": j.notes,
        "预警": j.warnings,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_stats(_: argparse.Namespace) -> None:
    repo = KnowledgeRepository()
    print(json.dumps(repo.stats(), ensure_ascii=False, indent=2))


def cmd_deliver(args: argparse.Namespace) -> None:
    """甲方招标清单 → 原表成本分析+去重链接（标准交付）。"""
    from src.knowledge.calibration import get_pair

    if args.project:
        pair = get_pair(args.project)
        if not pair:
            raise SystemExit(f"未知项目: {args.project}（见 config/project_pairs.json）")
        city = args.city or pair.get("city")
        tier = args.tier or pair.get("tier", "mid")
        tender_list = pair.get("tenders") or []
        if not tender_list:
            t = pair.get("tender") or pair.get("tender_fallback")
            tender_list = [t] if t else []
        export_list = pair.get("exports") or []
        if not export_list and pair.get("export"):
            export_list = [pair["export"]]
        if not tender_list:
            raise SystemExit(f"项目 {args.project} 未配置 tender 路径")
        materials_ref = pair.get("project_materials_ref")
        # link_inline / auto / cost_analysis：智能成本分析模板（自动识别甲方列并追加统一成本区）
        # 未配置 delivery 的老项目仍走原 inplace（校准回归用）
        delivery = pair.get("delivery") or "legacy"
        if delivery in ("link_inline", "auto", "cost_analysis"):
            from src.export.inline_cost_link import fill_inline_cost_link

            refs = [_resolve_file(p) for p in pair.get("reference_tenders") or []]
            sheets = pair.get("inline_sheets")
            if isinstance(sheets, str):
                sheets = [s.strip() for s in sheets.split(",") if s.strip()]
            tier_norm = (
                tier
                if tier not in ("高", "中", "低")
                else {"高": "high", "中": "mid", "低": "low"}[tier]
            )
            reports = []
            for i, tender in enumerate(tender_list):
                if len(tender_list) == 1:
                    out = args.output or pair.get("export") or (
                        export_list[0] if export_list else None
                    )
                else:
                    out = (
                        args.output
                        if args.output and len(tender_list) == 1
                        else (export_list[i] if i < len(export_list) else None)
                    )
                out_path = (
                    str(ROOT / out) if out and not Path(out).is_absolute() else out
                )
                report = fill_inline_cost_link(
                    _resolve_file(tender),
                    refs,
                    sheet_names=sheets,
                    output_path=out_path,
                    city=city,
                    tier=tier_norm,
                    project_materials_ref=materials_ref,
                )
                reports.append(report)
                print(
                    json.dumps(
                        {
                            "输出": report.output_path,
                            "模板": "智能成本分析",
                            "母行": report.masters,
                            "链接行": report.slaves,
                            "跨表链接": report.cross_sheet_slaves,
                            "引用": report.reference_hits,
                            "组价": report.judged,
                            "分表绑定": report.sheets,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            print(
                "下一步: 校正后 learn → python app.py calibrate --project",
                args.project,
            )
            return
        for i, tender in enumerate(tender_list):
            out = (
                args.output
                if args.output and len(tender_list) == 1
                else (export_list[i] if i < len(export_list) else None)
            )
            try:
                _run_deliver_one(
                    tender,
                    city=city,
                    tier=tier,
                    output=out,
                    args=args,
                    project_materials_ref=materials_ref,
                )
            except Exception as exc:
                fb = pair.get("tender_fallback")
                if fb and _resolve_file(tender) != _resolve_file(fb):
                    print(f"主招标失败({exc})，改用 tender_fallback: {fb}")
                    _run_deliver_one(
                        fb,
                        city=city,
                        tier=tier,
                        output=out,
                        args=args,
                        project_materials_ref=materials_ref,
                    )
                else:
                    raise
        print("下一步: 您校正后保存到 AI学习清单/ → python app.py calibrate --project", args.project)
        return

    if not args.file:
        raise SystemExit("请指定招标 file 或 --project")
    # 单文件招标默认走智能成本分析模板（自动接甲方列）
    from src.export.inline_cost_link import fill_inline_cost_link

    stem = Path(_resolve_file(args.file)).stem
    out = args.output or f"data/exports/{stem}_成本链接.xlsx"
    report = fill_inline_cost_link(
        _resolve_file(args.file),
        [],
        sheet_names=None,
        output_path=str(ROOT / out) if not Path(out).is_absolute() else out,
        city=args.city or "珠海",
        tier=args.tier or "mid",
        project_materials_ref=getattr(args, "materials_ref", None),
    )
    print(
        json.dumps(
            {
                "输出": report.output_path,
                "模板": "智能成本分析",
                "母行": report.masters,
                "链接行": report.slaves,
                "跨表链接": report.cross_sheet_slaves,
                "引用": report.reference_hits,
                "组价": report.judged,
                "分表绑定": report.sheets,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _run_deliver_one(
    tender: str,
    *,
    city: Optional[str],
    tier: str,
    output: Optional[str],
    args: argparse.Namespace,
    project_materials_ref: Optional[str] = None,
) -> None:
    tender_path = _resolve_file(tender)
    out_path = str(ROOT / output) if output and not Path(output).is_absolute() else output

    repo = KnowledgeRepository()
    result = repo.import_tender(tender_path, city=city, price_tier=tier)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    pr = _engine(args).run_for_project(result["project_id"])
    print("组价:", json.dumps(pr, ensure_ascii=False, indent=2))
    from src.export.inplace_bidder import fill_tender_inplace

    written = fill_tender_inplace(
        tender_path,
        pr["job_id"],
        output_path=out_path,
        reference_fill=not args.no_reference_fill,
        project_materials_ref=project_materials_ref,
    )
    print(f"已交付: {written}")


def cmd_regression(args: argparse.Namespace) -> None:
    """全项目校准 + audit-judge 回归（改 judge 后防回退）。"""
    from src.knowledge.calibration import run_regression_suite

    init_database()
    summary = run_regression_suite(
        audit_limit=args.audit_limit,
        min_calibrate_ratio=args.min_calibrate,
        min_audit_core=args.min_audit_core,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    out = ROOT / "data" / "exports" / "regression_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n摘要: {out}")
    if not summary.get("ok"):
        raise SystemExit(1)


def cmd_calibrate(args: argparse.Namespace) -> None:
    """对比系统导出 vs AI学习清单金标准，生成升级建议。"""
    from src.knowledge.calibration import (
        compare_calibration,
        export_calibration_report,
        get_pair,
        learn_from_gold,
        load_project_pairs,
        run_pair_calibration,
    )

    reports = []
    if args.project:
        reports.append(run_pair_calibration(args.project, rel_tol=args.rel_tol))
    elif args.all:
        for pair in load_project_pairs():
            try:
                reports.append(run_pair_calibration(pair["id"], rel_tol=args.rel_tol))
            except FileNotFoundError as e:
                print(f"跳过 {pair['id']}: {e}")
    elif args.gold and args.export:
        gold = _resolve_file(args.gold)
        ai = _resolve_file(args.export)
        reports.append(
            compare_calibration(
                gold,
                ai,
                project_id="custom",
                label=Path(gold).stem,
                rel_tol=args.rel_tol,
            )
        )
    else:
        raise SystemExit("请指定 --project ID、--all、或 --gold + --export")

    for rep in reports:
        path = export_calibration_report(rep, args.output if len(reports) == 1 else None)
        summary = {
            "项目": rep.label,
            "对比项": rep.compared,
            "±10%": f"{rep.within_10pct}/{rep.compared}",
            "±20%": f"{rep.within_20pct}/{rep.compared}",
            "金标准独有": rep.user_only,
            "系统独有": rep.ai_only,
            "合价偏差%": round(
                (rep.amount_ai - rep.amount_user) / rep.amount_user * 100, 1
            )
            if rep.amount_user
            else None,
            "升级建议": rep.upgrade_actions,
            "报告": path,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if args.learn:
            pair = get_pair(rep.project_id) if rep.project_id != "custom" else None
            gold_path = pair["gold"] if pair else args.gold
            if gold_path:
                r = learn_from_gold(
                    _resolve_file(gold_path),
                    city=(pair or {}).get("city", args.city or ""),
                    tier=(pair or {}).get("tier", args.tier or "mid"),
                )
                print(
                    f"已 learn 金标准: {gold_path} → {r.get('learned_records', 0)} 条"
                )
                ref = (pair or {}).get("project_materials_ref")
                if ref and pair:
                    from src.knowledge.project_materials import collect_st_prices_from_gold

                    st_r = collect_st_prices_from_gold(
                        _resolve_file(gold_path),
                        project_ref=ref,
                        project_name=pair.get("label", ref),
                        city=pair.get("city", args.city or ""),
                        price_tier=pair.get("tier", args.tier or "mid"),
                        code_prefixes=("ST", "MT") if ref == "haide_basement" else ("ST",),
                    )
                    print(
                        "已采集本项目编号价库:",
                        json.dumps(st_r, ensure_ascii=False),
                    )
    if args.learn and args.all:
        from src.knowledge.backfill_kb import backfill_projects_and_facts

        repo = KnowledgeRepository()
        conn = repo.conn()
        try:
            r = backfill_projects_and_facts(conn)
            conn.commit()
        finally:
            conn.close()
        print("已 backfill-kb:", json.dumps(r, ensure_ascii=False))


def cmd_extract_market_ref(args: argparse.Namespace) -> None:
    """从知识库提炼跨项目一致样本簇 → 市场参考价候选（人工审核后合并）。"""
    from src.pricing.extract_market_ref import build_report, export_report

    report = build_report(
        min_n=args.min_n,
        min_projects=args.min_projects,
        top=args.top,
        city=args.city,
    )
    out = export_report(report)
    cands = report["candidates"]
    covered = sum(1 for c in cands if c["already_covered"])
    print(
        f"候选簇 {len(cands)} 个（其中已覆盖 {covered}），"
        f"基于 {report['total_samples']} 条真实样本"
    )
    print(f"明细已导出: {out}")
    print("\n未覆盖候选（优先审核）:")
    for c in [x for x in cands if not x["already_covered"]][:15]:
        print(
            f"  [{c['n']}条/{len(c['projs'])}项目] {c['city']} {c['words']} "
            f"({c['unit']}) 主材{c['main_median']} 人工{c['lab_median']} "
            f"辅材{c['aux_median']} 机械{c['mach_median']}"
        )


def cmd_external_price(args: argparse.Namespace) -> None:
    """无样本项：外部搜索造价参考，写入 config/external_price_hints.json。"""
    from dataclasses import asdict

    from src.knowledge.calibration import get_pair, run_pair_calibration
    from src.pricing.external_reference import search_external_price

    if args.from_calibration and args.project:
        rep = run_pair_calibration(args.project)
        targets = [d for d in rep.worst if d.pct_diff is not None and abs(d.pct_diff) >= 20][: args.limit]
        pair_city = "深圳"
        from src.knowledge.calibration import get_pair

        p = get_pair(args.project)
        if p:
            pair_city = p.get("city", pair_city)
        for t in targets:
            hint = search_external_price(
                t.name,
                t.feature,
                t.unit,
                city=pair_city,
                fetch_web=not args.no_web,
            )
            print(json.dumps(asdict(hint), ensure_ascii=False, indent=2))
        return

    if not args.name:
        raise SystemExit("请指定 name，或使用 --from-calibration --project")
    hint = search_external_price(
        args.name,
        args.feature or "",
        args.unit or "㎡",
        city=args.city or "深圳",
        fetch_web=not args.no_web,
    )
    print(json.dumps(asdict(hint), ensure_ascii=False, indent=2))
    print("已追加到 config/external_price_hints.json；核实后可写入 market_reference_prices.json")


def cmd_sync(args: argparse.Namespace) -> None:
    """桌面 ↔ 手机同步。"""
    init_database()
    if args.sync_action == "serve":
        from src.sync.api import run_server

        run_server(host=args.host, port=args.port, reload=args.reload)
    elif args.sync_action == "bundle":
        from src.sync.bundle import write_sync_bundle

        path = write_sync_bundle(project_id=args.project)
        print(json.dumps({"bundle": str(path), "tip": "手机访问 sync serve 后打开 /"}, ensure_ascii=False))
    elif args.sync_action == "pull":
        from src.sync.corrections import export_corrections_json, list_corrections

        pending = list_corrections(project_id=args.project, status="pending")
        if not pending:
            print("无待同步的手机校正")
            return
        path = export_corrections_json(project_id=args.project)
        print(json.dumps({"exported": str(path), "count": len(pending)}, ensure_ascii=False, indent=2))
        print("下一步: 核对 JSON 后 learn 金标准 → python app.py calibrate --project … --learn")
    elif args.sync_action == "status":
        from src.sync.corrections import get_revision, list_corrections

        pending = list_corrections(status="pending")
        print(
            json.dumps(
                {"revision": get_revision(), "pending_corrections": len(pending)},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.sync_action == "token":
        from src.sync.config import CONFIG_PATH, ensure_api_token, get_api_token

        if args.show:
            t = get_api_token()
            print(json.dumps({"token": t or None, "config": str(CONFIG_PATH)}, ensure_ascii=False))
            if not t:
                print("未配置 Token，运行: python app.py sync token --new")
            return
        token = ensure_api_token(force_new=args.new)
        print(json.dumps({"token": token, "config": str(CONFIG_PATH)}, ensure_ascii=False, indent=2))
        print("请妥善保存 Token；手机「设置」页填入。外网请配合 Tailscale。")


def cmd_git_sync(args: argparse.Namespace) -> None:
    """将代码/配置/清单资料提交并 push 到 GitHub（huangweishi99-gif/GCZJXM-V1）。"""
    import subprocess

    if (ROOT / "config" / "sync_server.json").exists():
        text = (ROOT / "config" / "sync_server.json").read_text(encoding="utf-8")
        if '"api_token": "' in text and '""' not in text.split("api_token")[1][:30]:
            token_line = [ln for ln in text.splitlines() if "api_token" in ln]
            if token_line and '""' not in token_line[0] and "example" not in token_line[0]:
                print("警告: config/sync_server.json 含 Token，已加入 .gitignore，不会提交")

    msg = args.message or "sync: 组价系统更新"
    dry = ["git", "status", "--porcelain"]
    st = subprocess.run(dry, cwd=ROOT, capture_output=True, text=True, check=True)
    if not st.stdout.strip():
        print("工作区无变更，无需同步")
        return

    add = ["git", "add", "-A"]
    subprocess.run(add, cwd=ROOT, check=True)
    commit = subprocess.run(["git", "commit", "-m", msg], cwd=ROOT)
    if commit.returncode != 0:
        raise SystemExit("commit 失败（可能无 staged 变更）")
    if not args.no_push:
        push = subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT)
        if push.returncode != 0:
            raise SystemExit("push 失败，请检查网络或 GitHub 权限")
        print("已 push 到 origin:", msg)
    else:
        print("已 commit（未 push）:", msg)


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
    p_all.add_argument(
        "--audit",
        action="store_true",
        help="learn 完成后跑 audit-judge 并导出抽检报告",
    )
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

    p_inline = sub.add_parser(
        "link-inline",
        help="P列起成本区填母行；F/G/H桥接成本列；重复项lj链接（海德清单询格式）",
    )
    p_inline.add_argument("tender", nargs="?", default=None, help="招标清单 xlsx")
    p_inline.add_argument("--project", default=None, help="project_pairs 项目 id（如 haide_club_merge）")
    p_inline.add_argument(
        "--reference",
        nargs="+",
        required=True,
        help="可引用价格的 xlsx（可多个）",
    )
    p_inline.add_argument(
        "--sheets",
        default=None,
        help="逗号分隔 sheet 名；默认跳过说明/汇总",
    )
    p_inline.add_argument("--output", default=None)
    p_inline.add_argument("--materials-ref", default="haide_sales_office")
    _add_region_args(p_inline)
    p_inline.set_defaults(func=cmd_link_inline)

    sub.add_parser("backfill", help="为知识库回填做法标签（特征解析）").set_defaults(
        func=cmd_backfill
    )

    sub.add_parser(
        "backfill-kb",
        help="回填城市/档位并重建 line_price_facts、material_price_facts",
    ).set_defaults(func=cmd_backfill_kb)

    sub.add_parser(
        "backfill-cost-splits",
        help="整价无分项的历史成本按工艺份额回填人材机并重建价库",
    ).set_defaults(func=cmd_backfill_cost_splits)

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

    p_pm = sub.add_parser(
        "import-project-materials",
        help="导入项目主材编号价表（如售楼处主材料.xlsx）",
    )
    p_pm.add_argument("file", help="主材表 xlsx")
    p_pm.add_argument("--project", required=True, help="关联项目名称（如珠海海德公馆售楼处会所）")
    p_pm.add_argument("--ref", default=None, help="项目引用键（默认由项目名生成）")
    _add_region_args(p_pm)
    p_pm.set_defaults(func=cmd_import_project_materials)

    p_quota = sub.add_parser(
        "import-quota",
        help="导入广联达定额标准库（JSON格式，默认 config/quota_standards.json）",
    )
    p_quota.add_argument("file", nargs="?", default=None, help="定额JSON文件路径")
    p_quota.set_defaults(func=cmd_import_quota)

    p_q_match = sub.add_parser(
        "quota-match",
        help="测试定额匹配（根据项目名称和特征匹配定额子目）",
    )
    p_q_match.add_argument("name", help="项目名称")
    p_q_match.add_argument("--feature", default="", help="项目特征")
    p_q_match.add_argument("--unit", required=True, help="单位")
    p_q_match.add_argument("--top", type=int, default=5, help="返回前N个匹配结果")
    p_q_match.set_defaults(func=cmd_quota_match)

    p_q_cost = sub.add_parser(
        "quota-cost",
        help="计算定额子目成本",
    )
    p_q_cost.add_argument("code", help="定额编号")
    p_q_cost.add_argument("--unit", default="", help="目标单位（如 m、个、㎡）")
    _add_region_args(p_q_cost)
    p_q_cost.set_defaults(func=cmd_quota_cost)

    sub.add_parser(
        "audit-price",
        help="价格数量级审计：市场参考价/定额价/人工机械单价越界扫描",
    ).set_defaults(func=cmd_audit_price)

    p_boq = sub.add_parser(
        "validate-boq",
        help="招标清单可投标性体检（编码/名称/特征/单位/工程量 五要素）",
    )
    p_boq.add_argument("file", help="招标清单 xlsx/xls")
    p_boq.set_defaults(func=cmd_validate_boq)

    p_fee = sub.add_parser(
        "quote-fees",
        help="取费建议：成本单价→综合单价（管理费+利润+风险）及单位工程费汇总",
    )
    p_fee.add_argument("--cost", type=float, default=0, help="成本单价（元）")
    p_fee.add_argument("--quantity", type=float, default=1, help="工程量")
    p_fee.add_argument("--category", default="", help="工程类别：装饰装修/土建/安装/幕墙/市政")
    p_fee.add_argument("--tier", default="mid", help="档位：high/mid/low")
    p_fee.add_argument("--style", default="", help="项目风格：batch_fitout（批量精装 12%）")
    p_fee.set_defaults(func=cmd_quote_fees)

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
    p_audit.add_argument(
        "--include-simulated",
        action="store_true",
        help="包含模拟工程量/框架清单样本（默认排除，与 regression 口径一致）",
    )
    p_audit.add_argument(
        "--include-fee",
        action="store_true",
        help="包含费用项样本（默认排除，与 regression 口径一致）",
    )
    p_audit.set_defaults(func=cmd_audit_judge)

    p_review = sub.add_parser(
        "audit-review",
        help="基于 audit-judge 明细生成待确认清单（风险标签/建议动作）",
    )
    p_review.add_argument("--input", default=None, help="抽检报告路径（默认 data/exports/抽检报告_人材机判断.xlsx）")
    p_review.add_argument("--output", default=None, help="待确认清单 xlsx 输出路径")
    p_review.add_argument("--json-output", default=None, help="摘要 json 输出路径")
    p_review.add_argument("--top", type=int, default=80, help="导出最高风险前 N 行（默认 80；0=全部）")
    p_review.add_argument("--refresh", action="store_true", help="先刷新 audit-judge 抽检报告")
    p_review.add_argument("--limit", type=int, default=500, help="--refresh 时 audit-judge 抽检上限")
    p_review.add_argument(
        "--include-self",
        action="store_true",
        help="--refresh 时不排除同标准项（仅对比用）",
    )
    p_review.add_argument(
        "--include-simulated",
        action="store_true",
        help="--refresh 时包含模拟/框架样本（默认排除，与 regression 口径一致）",
    )
    p_review.add_argument(
        "--include-fee",
        action="store_true",
        help="--refresh 时包含费用项样本（默认排除，与 regression 口径一致）",
    )
    p_review.set_defaults(func=cmd_audit_review)

    p_deliver = sub.add_parser(
        "deliver",
        help="甲方招标清单→原表成本分析+去重链接（标准交付）",
    )
    p_deliver.add_argument("file", nargs="?", default=None, help="甲方招标 xlsx")
    p_deliver.add_argument(
        "--project",
        default=None,
        help="config/project_pairs.json 中的项目 id（如 haide_sales）",
    )
    _add_region_args(p_deliver)
    p_deliver.add_argument("--output", default=None)
    p_deliver.add_argument("--no-reference-fill", action="store_true")
    add_match_mode(p_deliver)
    p_deliver.set_defaults(func=cmd_deliver)

    p_cal = sub.add_parser("calibrate", help="对比系统导出 vs AI学习清单金标准")
    p_cal.add_argument("--project", default=None, help="project_pairs 项目 id")
    p_cal.add_argument("--all", action="store_true", help="校准全部已登记项目")
    p_cal.add_argument("--gold", default=None, help="金标准 xlsx（AI学习清单）")
    p_cal.add_argument("--export", default=None, help="系统导出 xlsx（data/exports）")
    p_cal.add_argument("--output", default=None, help="校准报告 json 路径")
    p_cal.add_argument(
        "--learn",
        action="store_true",
        help="校准后将金标准 learn 入库并 backfill-kb（--all 时）",
    )
    p_cal.add_argument("--rel-tol", type=float, default=0.10, help="行级偏差统计参考（默认10%%）")
    _add_region_args(p_cal)
    p_cal.set_defaults(func=cmd_calibrate)

    p_reg = sub.add_parser(
        "regression",
        help="全项目 calibrate + audit-judge 回归摘要（失败时 exit 1）",
    )
    p_reg.add_argument(
        "--audit-limit",
        type=int,
        default=500,
        help="audit-judge 抽检上限（默认 500）",
    )
    p_reg.add_argument(
        "--min-calibrate",
        type=float,
        default=0.95,
        help="各项目可比行 ±10%% 最低比例（默认 0.95）",
    )
    p_reg.add_argument(
        "--min-audit-core",
        type=float,
        default=0.45,
        help="audit-judge 主材+人工核心准确率下限（默认 0.45）",
    )
    p_reg.set_defaults(func=cmd_regression)

    p_ext = sub.add_parser("external-price", help="外部搜索造价参考（无样本项）")
    p_ext.add_argument("name", nargs="?", default=None, help="项目名称")
    p_ext.add_argument("--feature", default="")
    p_ext.add_argument("--unit", default="㎡")
    _add_region_args(p_ext)
    p_ext.add_argument("--no-web", action="store_true", help="仅生成搜索链接，不抓取网页")
    p_ext.add_argument("--from-calibration", action="store_true", help="对校准大偏差项批量搜索")
    p_ext.add_argument("--project", default=None, help="配合 --from-calibration")
    p_ext.add_argument("--limit", type=int, default=5)
    p_ext.set_defaults(func=cmd_external_price)

    p_mr = sub.add_parser(
        "extract-market-ref",
        help="从知识库提炼市场参考价候选（跨项目一致样本簇）",
    )
    p_mr.add_argument("--top", type=int, default=None, help="只输出前 N 个候选")
    p_mr.add_argument("--min-n", type=int, default=3, help="簇最小样本数（默认 3）")
    p_mr.add_argument("--min-projects", type=int, default=2, help="簇最小项目数（默认 2）")
    p_mr.add_argument("--city", default=None, help="只提炼指定城市")
    p_mr.set_defaults(func=cmd_extract_market_ref)

    p_sync = sub.add_parser("sync", help="桌面与手机端同步（清单校正）")
    sync_sub = p_sync.add_subparsers(dest="sync_action", required=True)
    p_serve = sync_sub.add_parser("serve", help="启动局域网同步服务 + 手机 Web")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--reload", action="store_true", help="开发热重载")
    p_serve.set_defaults(func=cmd_sync)
    p_bundle = sync_sub.add_parser("bundle", help="生成 latest_bundle.json")
    p_bundle.add_argument("--project", default=None, help="仅指定 project_pairs id")
    p_bundle.set_defaults(func=cmd_sync)
    p_pull = sync_sub.add_parser("pull", help="导出手机 pending 校正为 JSON")
    p_pull.add_argument("--project", default=None)
    p_pull.set_defaults(func=cmd_sync)
    p_status = sync_sub.add_parser("status", help="同步 revision / 待处理条数")
    p_status.set_defaults(func=cmd_sync)
    p_token = sync_sub.add_parser("token", help="生成/查看远程 API Token")
    p_token.add_argument("--new", action="store_true", help="强制重新生成")
    p_token.add_argument("--show", action="store_true", help="仅查看当前 Token")
    p_token.set_defaults(func=cmd_sync)

    p_git = sub.add_parser("git-sync", help="提交并 push 到 GitHub（Cursor 手机可见）")
    p_git.add_argument("-m", "--message", default=None, help="commit 说明")
    p_git.add_argument("--no-push", action="store_true", help="仅 commit 不 push")
    p_git.set_defaults(func=cmd_git_sync)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
