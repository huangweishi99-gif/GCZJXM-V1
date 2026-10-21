"""absorb_final.py — 定稿吸收：把用户确认的成本数据文件闭环入知识库。
触发语义：用户说"这个项目成本数据已经定稿/确认/吸收进数据库"时执行。
链路：备份 → 基线 audit → 登记 project_pairs gold → learn → 验证 is_verified → 复跑 audit 比对 → 报告。
用法:
  python absorb_final.py <定稿文件> --id <pair_id> --label <项目名> --city 深圳 --tier mid \
      [--quote-style metro_fitout] [--remark "..."] [--dry-run] [--skip-audit] [--limit 500]
硬性规则:
  - 先登记 gold 再 learn（is_verified 在 learn 时按 project_pairs 判定）
  - 旧版本定稿样本禁止删除（定稿优先聚合自动让旧版本让位，删样本实测掉准确率）
  - audit 回归非零 → 报告回滚点，不静默通过
"""
import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DB = ROOT / "data" / "cost_pricing.db"
PAIRS = ROOT / "config" / "project_pairs.json"
SUMMARY_JSON = ROOT / "data" / "exports" / "audit_judge_summary.json"
METRICS = [
    ("accuracy_all", "core_main_and_labor"),
    ("accuracy_all", "total_cost"),
    ("accuracy_auto_fill_only", "core_main_labor"),
]


def run_cli(args, timeout=1800):
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "app.py"), *args],
        cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    if r.returncode != 0:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        raise SystemExit(f"app.py {' '.join(args)} 失败 exit={r.returncode}")
    return r.stdout


def audit_metrics(limit):
    run_cli(["audit-judge", "--limit", str(limit), "--no-export"], timeout=1800)
    s = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    out = {}
    for grp, key in METRICS:
        v = (s.get(grp) or {}).get(key)
        if v is not None:
            out[f"{grp}.{key}"] = round(float(v), 4)
    out["samples"] = s.get("samples")
    return out


def register_pair(file_resolved, args):
    """登记/更新 project_pairs：gold 指向定稿文件。返回 (pair_dict, 旧gold或None)。"""
    data = json.loads(PAIRS.read_text(encoding="utf-8"))
    rel = str(file_resolved.relative_to(ROOT)) if _is_relative_to(file_resolved, ROOT) else str(file_resolved)
    rel = rel.replace("\\", "/")
    old_gold = None
    for it in data.get("pairs") or []:
        if it.get("id") == args.id:
            old_gold = it.get("gold")
            it["gold"] = rel
            it["label"] = args.label or it.get("label", "")
            it["city"] = args.city or it.get("city", "")
            it["tier"] = args.tier or it.get("tier", "mid")
            if args.quote_style:
                it["quote_style"] = args.quote_style
            if args.remark:
                it["remark"] = args.remark
            break
    else:
        pair = {
            "id": args.id,
            "label": args.label or args.id,
            "gold": rel,
            "city": args.city or "",
            "tier": args.tier or "mid",
        }
        if args.quote_style:
            pair["quote_style"] = args.quote_style
        if args.remark:
            pair["remark"] = args.remark
        data.setdefault("pairs", []).append(pair)
    return data, rel, old_gold


def _is_relative_to(p, parent):
    try:
        p.relative_to(parent)
        return True
    except ValueError:
        return False


def verify_verified(project_id):
    db = sqlite3.connect(DB)
    total, verified = db.execute(
        "SELECT COUNT(*), SUM(is_verified) FROM cost_records WHERE source_project_id=?",
        (project_id,)).fetchone()
    db.close()
    return total or 0, int(verified or 0)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file", help="定稿成本文件（xls/xlsx）")
    p.add_argument("--id", required=True, help="project_pairs 项目代号（英文下划线）")
    p.add_argument("--label", default="", help="项目中文名")
    p.add_argument("--city", required=True)
    p.add_argument("--tier", default="mid")
    p.add_argument("--quote-style", default="")
    p.add_argument("--remark", default="")
    p.add_argument("--limit", type=int, default=500, help="audit 抽样数（>池则全量）")
    p.add_argument("--dry-run", action="store_true", help="只打印计划，不执行")
    p.add_argument("--skip-audit", action="store_true", help="跳过前后 audit（不推荐）")
    a = p.parse_args()

    fp = Path(a.file).resolve()
    if not fp.exists():
        raise SystemExit(f"文件不存在: {fp}")

    print(f"== 定稿吸收计划 ==\n  文件: {fp}\n  代号: {a.id}  城市: {a.city}  档位: {a.tier}")
    data, rel, old_gold = register_pair(fp, a)
    if old_gold and Path(ROOT / old_gold).resolve() != fp:
        print(f"  旧 gold: {old_gold}（样本保留，定稿优先聚合自动让位）")
    print(f"  新 gold: {rel}")
    if a.dry_run:
        print("[dry-run] 未执行任何写入。")
        return

    # 1) 备份
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_bak = DB.with_name(f"{DB.name}.bak_{stamp}")
    pairs_bak = PAIRS.with_suffix(".json.bak_" + stamp)
    shutil.copy2(DB, db_bak)
    shutil.copy2(PAIRS, pairs_bak)
    print(f"\n[1/5] 备份: {db_bak.name} / {pairs_bak.name}")

    # 2) 基线 audit（learn 前）
    before = {}
    if not a.skip_audit:
        print(f"[2/5] 基线 audit-judge --limit {a.limit} ...")
        before = audit_metrics(a.limit)
        print(f"      基线: {before}")

    # 3) 登记 gold
    PAIRS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[3/5] project_pairs.json 已登记 gold")

    # 4) learn
    print("[4/5] learn ...")
    out = run_cli(["learn", str(fp), "--name", a.label or a.id,
                   "--city", a.city, "--tier", a.tier], timeout=3600)
    i = out.find("{")
    if i >= 0:
        try:
            result, _ = json.JSONDecoder().raw_decode(out[i:])
        except json.JSONDecodeError:
            result = {}
    else:
        result = {}
    pid = result.get("project_id")
    print(f"      project_id={pid}  学入记录={result.get('learned_records')}  "
          f"跳过无成本={result.get('skipped_no_cost')}")

    # 5) 验证 + 复跑 audit
    total, verified = verify_verified(pid)
    print(f"[5/5] is_verified 验证: {verified}/{total} 条定稿样本")
    if verified == 0 and total > 0:
        print("!! is_verified=0：gold 登记可能未生效（路径必须 normcase 匹配），"
              f"回滚点 {db_bak.name}")
    if not a.skip_audit:
        print("      复跑 audit-judge ...")
        after = audit_metrics(a.limit)
        print(f"      吸收后: {after}")
        acc_keys = [k for k in after if k != "samples"]  # samples 是抽样计数非精度指标
        reg = {k: (before.get(k), after.get(k)) for k in acc_keys
               if before.get(k) is not None and float(after[k]) < float(before[k]) - 1e-9}
        improved = {k: (before.get(k), after.get(k)) for k in acc_keys
                    if before.get(k) is not None and float(after[k]) > float(before[k]) + 1e-9}
        if improved:
            print(f"      指标提升（吸收贡献）: {improved}")
        if reg:
            print(f"\n!! 回归告警 {reg}")
            print(f"   回滚: 关库后 copy {db_bak.name} 覆盖 cost_pricing.db；git restore config/project_pairs.json")
        else:
            print("\n== 吸收完成：无回归 ==")
    print(f"回滚点: data/{db_bak.name}")


if __name__ == "__main__":
    main()
