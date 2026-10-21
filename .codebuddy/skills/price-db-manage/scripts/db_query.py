"""db_query.py — 组价数据库查询与零星录入。
用法:
  python db_query.py material <关键词> [--city 深圳]     查材料价
  python db_query.py line <清单项名> [--city 深圳]       查清单项历史价
  python db_query.py quota <关键词>                       查定额子目
  python db_query.py add-material --name 铜闸门 --spec DN300 --unit 个 --city 深圳 --price 8500 --source 厂家询价2026-10
"""
import argparse
import sqlite3
import sys

DB = r"d:/projects/cost-estimation/data/cost_pricing.db"


def q(sql, args=()):
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    rows = db.execute(sql, args).fetchall()
    db.close()
    return rows


def cmd_material(kw, city):
    sql = """SELECT material_key, material_category, spec_text, unit_norm, city, price_tier,
                    ROUND(material_main,2) price, sample_count, updated_at
             FROM material_price_facts WHERE material_key LIKE ?"""
    args = [f"%{kw}%"]
    if city:
        sql += " AND city=?"
        args.append(city)
    sql += " ORDER BY sample_count DESC LIMIT 30"
    for r in q(sql, args):
        print(dict(r))
    if not q(sql.replace("LIMIT 30", "LIMIT 1"), args):
        print("(无结果，试试英文类名如 cable/steel/sand，或查 market_reference_prices.json)")


def cmd_line(kw, city):
    sql = """SELECT s.name_norm, s.unit_norm, f.city, f.price_tier,
                    ROUND(f.material_main,2) 主材, ROUND(f.labor,2) 人工,
                    ROUND(f.material_aux,2) 辅材, ROUND(f.machinery,2) 机械,
                    ROUND(f.cost_unit_price,2) 成本单价, f.sample_count
             FROM line_price_facts f JOIN standard_items s ON s.id=f.standard_item_id
             WHERE s.name_norm LIKE ?"""
    args = [f"%{kw}%"]
    if city:
        sql += " AND f.city=?"
        args.append(city)
    sql += " ORDER BY f.sample_count DESC LIMIT 30"
    rows = q(sql, args)
    for r in rows:
        print(dict(r))
    if not rows:
        print("(无历史价事实)")


def cmd_quota(kw):
    rows = q("""SELECT quota_code, name, unit, labor_consumption, craft_category, substr(work_content,1,60) wc
                FROM quota_standards WHERE name LIKE ? OR quota_code LIKE ? LIMIT 20""",
             [f"%{kw}%", f"%{kw}%"])
    for r in rows:
        print(dict(r))
    if not rows:
        print("(无定额子目)")


def cmd_add_material(a):
    key = a.name
    db = sqlite3.connect(DB)
    db.execute(
        """INSERT INTO material_price_facts
           (material_key, material_category, spec_text, unit_norm, city, price_tier, material_main, sample_count)
           VALUES (?,?,?,?,?,?,?,1)
           ON CONFLICT(material_key, unit_norm, city, price_tier)
           DO UPDATE SET material_main=excluded.material_main,
                         sample_count=sample_count+1,
                         spec_text=excluded.spec_text,
                         updated_at=datetime('now','localtime')""",
        (key, a.category or "", a.spec or "", a.unit, a.city or "", a.tier or "mid", a.price),
    )
    db.commit()
    db.close()
    print(f"已录入: {key} {a.spec or ''} {a.price}元/{a.unit} ({a.city})  source={a.source}  [未跑回归，请跑 audit-judge --limit 500]")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    m = sub.add_parser("material")
    m.add_argument("kw")
    m.add_argument("--city", default="")
    l = sub.add_parser("line")
    l.add_argument("kw")
    l.add_argument("--city", default="")
    qu = sub.add_parser("quota")
    qu.add_argument("kw")
    am = sub.add_parser("add-material")
    am.add_argument("--name", required=True)
    am.add_argument("--spec", default="")
    am.add_argument("--unit", required=True)
    am.add_argument("--city", default="")
    am.add_argument("--price", type=float, required=True)
    am.add_argument("--category", default="")
    am.add_argument("--tier", default="mid")
    am.add_argument("--source", default="")
    a = p.parse_args()
    if a.cmd == "material":
        cmd_material(a.kw, a.city)
    elif a.cmd == "line":
        cmd_line(a.kw, a.city)
    elif a.cmd == "quota":
        cmd_quota(a.kw)
    elif a.cmd == "add-material":
        if not a.source:
            print("add-material 必须提供 --source（价格出处），禁止无源录入")
            sys.exit(1)
        cmd_add_material(a)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
