"""craft_db.py — 工艺工序链数据库（craft_processes 表）管理。
用法:
  python craft_db.py init                      建表 + 灌入种子（assets/craft_processes_seed.json，可重复执行=upsert）
  python craft_db.py query <关键词>            按分项名模糊查工序链
  python craft_db.py add --item 块料墙面 --trade 装饰装修 --unit ㎡ \
      --steps "基层清理→砂浆找平→铺贴→擦缝" --missing "规格未写" --anchor "020003-XX" --source "某项目复核"
设计: 组价八步法第 4 步"拆解工艺流程"先查本表，再对照项目特征找缺漏/多余。
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DB = ROOT / "data" / "cost_pricing.db"
SEED = Path(__file__).resolve().parents[1] / "assets" / "craft_processes_seed.json"

DDL = """
CREATE TABLE IF NOT EXISTS craft_processes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    item_key       TEXT NOT NULL UNIQUE,
    trade          TEXT NOT NULL DEFAULT '',
    unit_hint      TEXT NOT NULL DEFAULT '',
    process_chain  TEXT NOT NULL DEFAULT '[]',
    missing_alerts TEXT NOT NULL DEFAULT '[]',
    price_anchor   TEXT NOT NULL DEFAULT '',
    source         TEXT NOT NULL DEFAULT '',
    updated_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
)
"""


def _conn():
    return sqlite3.connect(DB)


def upsert(item_key, trade, unit_hint, process_chain, missing_alerts, price_anchor, source):
    """process_chain: list[{step, materials[], note}] 或 '→'分隔字符串; missing_alerts: list 或 '；'分隔。"""
    if isinstance(process_chain, str):
        process_chain = [{"step": s.strip(), "materials": [], "note": ""}
                         for s in process_chain.replace("->", "→").split("→") if s.strip()]
    if isinstance(missing_alerts, str):
        missing_alerts = [s.strip() for s in missing_alerts.replace(";", "；").split("；") if s.strip()]
    db = _conn()
    db.execute(
        """INSERT INTO craft_processes (item_key, trade, unit_hint, process_chain, missing_alerts, price_anchor, source)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(item_key) DO UPDATE SET
             trade=excluded.trade, unit_hint=excluded.unit_hint,
             process_chain=excluded.process_chain, missing_alerts=excluded.missing_alerts,
             price_anchor=excluded.price_anchor, source=excluded.source,
             updated_at=datetime('now','localtime')""",
        (item_key, trade, unit_hint,
         json.dumps(process_chain, ensure_ascii=False),
         json.dumps(missing_alerts, ensure_ascii=False),
         price_anchor, source),
    )
    db.commit()
    db.close()


def cmd_init():
    db = _conn()
    db.execute(DDL)
    db.commit()
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    for it in seed:
        upsert(it["item_key"], it.get("trade", ""), it.get("unit_hint", ""),
               it.get("process_chain", []), it.get("missing_alerts", []),
               it.get("price_anchor", ""), it.get("source", ""))
    n = db.execute("SELECT COUNT(*) FROM craft_processes").fetchone()[0]
    print(f"craft_processes 就绪：{n} 条（种子 {len(seed)} 条已 upsert）")


def _median(xs):
    xs = sorted(xs)
    m = len(xs)
    return xs[m // 2] if m % 2 else (xs[m // 2 - 1] + xs[m // 2]) / 2


def cmd_seed_quota():
    """从 quota_standards 按定额章节聚合材料构成，反灌工艺候选。
    背景：work_content/craft_category 导入时未填充（实测全 NULL），工序文本不可用；
    可用的是 material_json（人材机消耗量）。故候选形态=「章节→高频材料+消耗中位」材料构成包，
    供八步法第5步"逐工序人材机"提示材料，不替代工序顺序（工序仍按项目特征拆）。
    item_key=quotacat:<章节>，source=定额材料构成；确认可用后可用 add 转为正式工艺。"""
    db = _conn()
    if not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quota_standards'").fetchone():
        print("quota_standards 表不存在")
        sys.exit(1)
    rows = db.execute(
        "SELECT chapter, unit, material_json FROM quota_standards"
        " WHERE chapter IS NOT NULL AND trim(chapter) != ''").fetchall()
    groups = {}
    for chapter, unit, mj in rows:
        try:
            mats = json.loads(mj or "{}")
        except json.JSONDecodeError:
            continue
        g = groups.setdefault(chapter, {"units": set(), "mats": {}})
        if unit:
            g["units"].add(unit)
        for name, arr in mats.items():
            if isinstance(arr, list) and arr and isinstance(arr[0], (int, float)) and arr[0] > 0:
                g["mats"].setdefault(name, []).append(arr[0])
    added = 0
    for chapter, g in groups.items():
        ranked = sorted(g["mats"].items(), key=lambda kv: -len(kv[1]))[:12]
        if not ranked:
            continue
        mats = [f"{name}(×{_median(v):g})" for name, v in ranked]
        chain = [{"step": "定额材料构成包（按项目特征选定额子目后逐工序归集）",
                  "materials": mats,
                  "note": f"聚合{len(g['mats'])}种材料/消耗量为中位，口径单位 {'/'.join(sorted(g['units']))[:30]}"}]
        cur = db.execute(
            "INSERT OR IGNORE INTO craft_processes"
            " (item_key, trade, unit_hint, process_chain, missing_alerts, price_anchor, source)"
            " VALUES (?,?,?,?,?,?,?)",
            ("quotacat:" + chapter, chapter, "/".join(sorted(g["units"]))[:20],
             json.dumps(chain, ensure_ascii=False),
             json.dumps(["候选仅为材料构成提示，工序顺序按项目特征拆解"]),
             f"定额章节:{chapter}", "定额材料构成"))
        added += cur.rowcount
    db.commit()
    n = db.execute("SELECT COUNT(*) FROM craft_processes").fetchone()[0]
    print(f"定额材料构成候选：{len(rows)} 行定额 → {len(groups)} 章节组，新增 {added} 条，craft_processes 共 {n} 条")


def cmd_query(kw):
    db = _conn()
    if not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='craft_processes'").fetchone():
        print("表不存在，先跑: python craft_db.py init")
        sys.exit(1)
    rows = db.execute(
        "SELECT * FROM craft_processes WHERE item_key LIKE ? OR trade LIKE ?"
        " ORDER BY (source='定额work_content'), trade, item_key LIMIT 25",
        (f"%{kw}%", f"%{kw}%")).fetchall()
    if not rows:
        print(f"(无「{kw}」相关工艺，可 craft_db.py add 补录，或 craft_db.py seed-quota 后重查)")
        return
    for r in rows:
        tag = " [定额候选]" if r[7] == "定额材料构成" else ""
        print(f"== {r[1]} [{r[2]}] 单位 {r[3] or '-'}{tag}  锚: {r[6]}")
        for i, step in enumerate(json.loads(r[4]), 1):
            mats = "+".join(step.get("materials") or [])
            note = f"（{step['note']}）" if step.get("note") else ""
            print(f"   {i}. {step['step']}{note}{' <- ' + mats if mats else ''}")
        alerts = json.loads(r[5])
        if alerts:
            print(f"   ⚠ 缺漏高发: {'；'.join(alerts)}")
        print()


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("init")
    sub.add_parser("seed-quota", help="从定额work_content反灌工序候选")
    q = sub.add_parser("query")
    q.add_argument("kw")
    a = sub.add_parser("add")
    a.add_argument("--item", required=True)
    a.add_argument("--trade", default="")
    a.add_argument("--unit", default="")
    a.add_argument("--steps", required=True, help="工序链，→ 分隔")
    a.add_argument("--missing", default="", help="缺漏高发点，；分隔")
    a.add_argument("--anchor", default="")
    a.add_argument("--source", default="手工补录")
    args = p.parse_args()
    if args.cmd == "init":
        cmd_init()
    elif args.cmd == "seed-quota":
        cmd_seed_quota()
    elif args.cmd == "query":
        cmd_query(args.kw)
    elif args.cmd == "add":
        upsert(args.item, args.trade, args.unit, args.steps, args.missing, args.anchor, args.source)
        print(f"已补录: {args.item}（记得在组价时对照项目特征验证）")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
