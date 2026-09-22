# -*- coding: utf-8 -*-
"""audit-judge 结果分析工具集（由根目录 _tmp_*.py 临时脚本正式化而来）。

所有路径按项目根解析，cwd 任意均可运行；控制台为 GBK 时需 utf-8 输出（本文件已处理）。

用法:
    python scripts/audit_tools.py metric [口径标签]              # 打印 audit_judge_summary.json 关键指标
    python scripts/audit_tools.py ver_stat [xlsx]                # 定稿/过程稿拆分 + 来源分布 + 失败明细
    python scripts/audit_tools.py rule_stat [min_fail] [xlsx]    # 按判定价签名聚合 market_reference（找纯亏损规则）
    python scripts/audit_tools.py src_dump <来源名> [xlsx]       # 按判断来源 dump 实/判/conf/auto/OK
    python scripts/audit_tools.py drill [xlsx]                   # 失败钻取，写出 audit_drill_*.txt
    python scripts/audit_tools.py note <record_id[,id...]>       # 单条命中规则与特征文本
    python scripts/audit_tools.py query <关键词>                 # 全库检索 cost_records 同键实值分布

典型流程（改 market_reference 规则前后各跑一次对比）:
    python app.py audit-judge --limit 500                        # 基线口径（373 真实样本）
    python app.py audit-judge --limit 500 --gold-only --output data/exports/抽检报告_定稿口径.xlsx
    python scripts/audit_tools.py metric 基线
    python scripts/audit_tools.py rule_stat 2 data/exports/抽检报告_定稿口径.xlsx
    python scripts/audit_tools.py query "涂膜防水"                # 确认同键是否分裂（定稿/过程稿两批）
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_XLSX = ROOT / "data" / "exports" / "抽检报告_人材机判断.xlsx"
SUMMARY = ROOT / "data" / "exports" / "audit_judge_summary.json"


def _fmt(v):
    import pandas as pd

    return "-" if pd.isna(v) else f"{float(v):g}"


def _load(xlsx=None):
    import pandas as pd

    return pd.read_excel(Path(xlsx) if xlsx else DEFAULT_XLSX, sheet_name="明细")


def cmd_metric(args):
    """打印 audit_judge_summary.json 关键指标。"""
    import json

    tag = args[0] if args else "基线"
    d = json.load(open(SUMMARY, encoding="utf-8"))
    a = d["accuracy_all"]
    print(
        f"[{tag}] n={d['samples']} core={a['core_main_and_labor']} total={a['total_cost']} "
        f"auto={d['auto_fill_rate']} main={a['material_main']} labor={a['labor']} aux={a['material_aux']} "
        f"| filters={d['filters']}"
    )


def cmd_ver_stat(args):
    """按「定稿/过程稿」拆分准确率：判定残余失败是否主要来自旧版本样本。"""
    src_path = Path(args[0]) if args else DEFAULT_XLSX
    df = _load(src_path)
    print(f"# 来源: {src_path}")

    from src.db.database import get_connection

    conn = get_connection(None)
    cur = conn.cursor()
    cur.execute(
        "select cr.id, cr.is_verified, p.name, p.city from cost_records cr "
        "left join projects p on p.id = cr.source_project_id"
    )
    meta = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
    conn.close()

    df["定稿"] = df["record_id"].map(lambda i: bool((meta.get(int(i)) or (0,))[0]))
    df["项目"] = df["record_id"].map(lambda i: (meta.get(int(i)) or ("", "", ""))[1])

    for label, g in [("定稿样本", df[df["定稿"]]), ("过程稿样本", df[~df["定稿"]])]:
        n = len(g)
        ok = int((g["核心OK"] == True).sum())
        print(f"{label}: {n} 行, core_ok={ok} ({(ok / n if n else 0):.4f}), "
              f"auto_fill={float(g['可自动填'].mean()):.4f}")

    print("\n=== 过程稿样本按项目 ===")
    for proj, g in df[~df["定稿"]].groupby("项目"):
        ok = int((g["核心OK"] == True).sum())
        print(f"  {str(proj)[:40]:<40} {len(g):>3} 行 core_ok={ok}/{len(g)}")

    print("\n=== 残余失败中过程稿占比 ===")
    f = df[df["核心OK"] == False]
    print(f"  失败 {len(f)} 行, 其中过程稿 {int((~f['定稿']).sum())} 行, 定稿 {int(f['定稿'].sum())} 行")

    print("\n=== 失败按来源计数 ===")
    print(df[df["核心OK"] == False]["判断来源"].value_counts().to_string())
    print("\n=== 全部按来源 ===")
    for s, g in df.groupby("判断来源"):
        n = len(g)
        print(f"  {s:<32} {n:>4} 行 core={int((g['核心OK'] == True).sum()) / n:.4f} "
              f"auto={float(g['可自动填'].mean()):.4f}")

    print("\n=== 定稿样本的残余失败（规则应修的部分）===")
    gf = df[(df["核心OK"] == False) & df["定稿"]]
    for src, g in gf.groupby("判断来源"):
        print(f"\n-- {src} ({len(g)} 行) --")
        for _, r in g.iterrows():
            print(f"  #{r['record_id']} {r['城市']} | {str(r['项目名称'])[:30]} [{r['单位']}]")
            print(f"      实[主{_fmt(r['实_主材'])} 人{_fmt(r['实_人工'])} 辅{_fmt(r['实_辅材'])} 机{_fmt(r['实_机械'])}]"
                  f"  判[主{_fmt(r['判_主材'])} 人{_fmt(r['判_人工'])} 辅{_fmt(r['判_辅材'])} 机{_fmt(r['判_机械'])}]")


def cmd_rule_stat(args):
    """按判定价签名聚合 market_reference 行，找失败>>成功的规则（纯亏损规则）。"""
    min_fail = int(args[0]) if args else 2
    xlsx = args[1] if len(args) > 1 else None
    df = _load(xlsx)
    mr = df[df["判断来源"] == "market_reference"].copy()
    keys = ["判_主材", "判_人工", "判_辅材", "判_机械"]
    mr["sig"] = mr[keys].apply(lambda r: "/".join(_fmt(v) for v in r), axis=1)

    rows = []
    for sig, g in mr.groupby("sig"):
        ok = int((g["核心OK"] == True).sum())
        fail = int((g["核心OK"] == False).sum())
        rows.append((fail, ok, sig, g))
    rows.sort(key=lambda x: (-x[0], x[1]))

    print(f"\n=== market_reference 共 {len(mr)} 行, 判签分组 {len(rows)} 个; 展示 fail>={min_fail} ===")
    for fail, ok, sig, g in rows:
        if fail < min_fail:
            continue
        print(f"\n[判 {sig}]  OK={ok} FAIL={fail}")
        for _, r in g.iterrows():
            tag = "OK  " if r["核心OK"] else "FAIL"
            print(f"   {tag} {r.get('城市')}/{r.get('工艺')} | {str(r['项目名称'])[:34]} [{r['单位']}] "
                  f"实[主{_fmt(r['实_主材'])} 人{_fmt(r['实_人工'])} 辅{_fmt(r['实_辅材'])} 机{_fmt(r['实_机械'])}]")


def cmd_src_dump(args):
    """按判断来源 dump 抽检明细（实/判/conf/auto/OK）。"""
    if not args:
        print("用法: python scripts/audit_tools.py src_dump <来源名> [xlsx]")
        return
    src = args[0]
    df = _load(args[1] if len(args) > 1 else None)
    g = df[df["判断来源"] == src]
    print(f"=== {src}: {len(g)} 行, core_ok={int((g['核心OK'] == True).sum())} ===")
    for _, r in g.sort_values(["城市", "项目名称"]).iterrows():
        tag = "OK  " if r["核心OK"] else "FAIL"
        print(f"{tag} #{r['record_id']} {r['城市']}/{r['档位']} | {r['项目名称']} [{r['单位']}] "
              f"conf={r['置信度']:.2f} auto={r['可自动填']}")
        print(f"      实[主{_fmt(r['实_主材'])} 人{_fmt(r['实_人工'])} 辅{_fmt(r['实_辅材'])} 机{_fmt(r['实_机械'])}]"
              f"  判[主{_fmt(r['判_主材'])} 人{_fmt(r['判_人工'])} 辅{_fmt(r['判_辅材'])} 机{_fmt(r['判_机械'])}]")


def cmd_drill(args):
    """失败钻取：按来源列出全部失败行，并另存 market_reference 全量行（用于同键分析）。"""
    import pandas as pd

    xlsx = Path(args[0]) if args else DEFAULT_XLSX
    df = pd.read_excel(xlsx, sheet_name="明细")
    out_dir = ROOT / "data" / "exports"
    fail_path = out_dir / "audit_drill_fail.txt"
    mr_path = out_dir / "audit_drill_mr_all.txt"

    def fmt(v):
        return f"{v:.1f}" if pd.notna(v) else "—"

    fail = df[df["核心OK"] == False].copy().sort_values(["判断来源", "置信度"])
    with open(fail_path, "w", encoding="utf-8") as fh:

        def p(*a):
            s = " ".join(str(x) for x in a)
            print(s, flush=True)
            fh.write(s + "\n")

        for src, g in fail.groupby("判断来源", sort=True):
            tot = len(df[df["判断来源"] == src])
            p(f"\n===== 来源: {src}  失败 {len(g)} / {tot} =====")
            for _, r in g.iterrows():
                p(f"[{src}] conf={r['置信度']:.2f} auto={r['可自动填']} | {r['城市']}/{r['档位']} {r['工艺']}")
                p(f"   行: {r['项目名称']}  单位={r['单位']}")
                p(f"   实[主{fmt(r['实_主材'])} 人{fmt(r['实_人工'])} 辅{fmt(r['实_辅材'])} 机{fmt(r['实_机械'])}] 合{fmt(r['实_合计'])}")
                p(f"   判[主{fmt(r['判_主材'])} 人{fmt(r['判_人工'])} 辅{fmt(r['判_辅材'])} 机{fmt(r['判_机械'])}] 合{fmt(r['判_合计'])}")

    mr = df[df["判断来源"] == "market_reference"].copy()
    with open(mr_path, "w", encoding="utf-8") as fh:
        for _, r in mr.sort_values(["项目名称"]).iterrows():
            ok = "OK" if r["核心OK"] else "FAIL"
            fh.write(f"{ok} | {r['城市']}/{r['档位']} {r['工艺']} | {r['项目名称']} [{r['单位']}] "
                     f"实[主{fmt(r['实_主材'])} 人{fmt(r['实_人工'])} 辅{fmt(r['实_辅材'])} 机{fmt(r['实_机械'])}] "
                     f"判[主{fmt(r['判_主材'])} 人{fmt(r['判_人工'])} 辅{fmt(r['判_辅材'])} 机{fmt(r['判_机械'])}] "
                     f"conf={r['置信度']:.2f}\n")
    print(f"\n已写出: {fail_path}\n已写出: {mr_path}（market_reference {len(mr)} 行）")


def cmd_note(args):
    """打印指定 record_id 的判断明细（source/rule/note/分量）。"""
    if not args:
        print("用法: python scripts/audit_tools.py note <record_id[,id...]>")
        return
    from src.db.database import get_connection
    from src.knowledge.repository import KnowledgeRepository
    from src.pricing.component_judge import PricingContext, judge_line_components
    from src.pricing.engine import PricingEngine

    ids = [int(x) for x in args[0].split(",")]
    conn = get_connection(None)
    cur = conn.cursor()
    repo = KnowledgeRepository(None)
    engine = PricingEngine(None)
    for rid in ids:
        cur.execute(
            "select cr.standard_item_id, si.name_norm, si.feature_norm, si.unit_norm, "
            "p.city, cr.material_main, cr.material_aux, cr.labor, cr.machinery "
            "from cost_records cr join standard_items si on si.id=cr.standard_item_id "
            "left join projects p on p.id=cr.source_project_id where cr.id=?",
            (rid,),
        )
        sid, name, feature, unit, city, m, aux, lab, mach = cur.fetchone()
        print(f"--- {rid} {name[:40]}")
        print(f"    特征: {(feature or '')[:220]}")
        j = judge_line_components(name, feature or "", unit, engine, repo,
                                  ctx=PricingContext(city=city, price_tier="mid"),
                                  exclude_standard_item_id=sid)
        d = j.__dict__
        p = j.as_components()
        print(f"    source={j.source} rule={d.get('rule_id') or d.get('matched_rule') or d.get('note')}")
        for k, v in d.items():
            if k in ("components", "craft_breakdown"):
                continue
            print(f"    {k} = {v}")
        print(f"    实 主{m or 0}/人{lab or 0}/辅{aux or 0}/机{mach or 0}   判 {p}")
    conn.close()


def cmd_query(args):
    """全库检索 cost_records（join standard_items/projects），用于确认同键是否口径分裂。"""
    if not args:
        print("用法: python scripts/audit_tools.py query <关键词>")
        return
    from src.db.database import get_connection

    kw = args[0]
    conn = get_connection(None)
    cur = conn.cursor()
    cur.execute(
        "select cr.id, p.name, p.city, si.unit_norm, si.name_norm, si.feature_norm, "
        "cr.material_main, cr.material_aux, cr.labor, cr.machinery, cr.is_verified "
        "from cost_records cr "
        "join standard_items si on si.id = cr.standard_item_id "
        "left join projects p on p.id = cr.source_project_id "
        "where si.name_norm like ? or si.feature_norm like ?",
        (f"%{kw}%", f"%{kw}%"),
    )
    rows = cur.fetchall()
    conn.close()
    for r in rows:
        print(f"{r[0]:>6} {str(r[1])[:18]:<18} [{r[2] or '-':<3}] {r[3]:<3} "
              f"实[主{r[6] or 0:>9.2f} 人{r[8] or 0:>7.2f} 辅{r[7] or 0:>6.2f} 机{r[9] or 0:>5.2f}] "
              f"gold={r[10]} | {r[4][:32]} | {(r[5] or '')[:44]}")
    print(f"共 {len(rows)} 行")


COMMANDS = {
    "metric": cmd_metric,
    "ver_stat": cmd_ver_stat,
    "rule_stat": cmd_rule_stat,
    "src_dump": cmd_src_dump,
    "drill": cmd_drill,
    "note": cmd_note,
    "query": cmd_query,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
