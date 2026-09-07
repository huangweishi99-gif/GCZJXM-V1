# -*- coding: utf-8 -*-
"""临时：电气桶 auto-bad 全行。"""
import io, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

rows = json.loads(open(r"d:\projects\cost-estimation\data\tmp\_mep_rows.json", encoding="utf-8").read())

ab = [x for x in rows if x["auto"] and not x["core_ok"]]
for x in ab:
    m = re.match(r"\[([^\]]+)\]", x["notes"] or "")
    tag = m.group(1) if m else ""
    if tag != "电气":
        continue
    rel = "" if x["a_main"] <= 0 else f"{(x['p_main']-x['a_main'])/x['a_main']*100:+.0f}%"
    feat1 = re.split(r"[\n\r]", x["feature"] or "")
    f1 = ""
    for ln in feat1:
        if "名称" in ln and "：" in ln or ":" in ln:
            f1 = ln[:40]
            break
    print(f"[{x['record_id']}] p{x['project_id']:<3} 主{x['a_main']:>7.1f}->{x['p_main']:>7.1f}({rel:>5}) 人{x['a_labor']:>6.1f}->{x['p_labor']:>6.1f} | {x['name'][:30]:<30} | {x['feature'][:42].replace(chr(10),' / ')}")
