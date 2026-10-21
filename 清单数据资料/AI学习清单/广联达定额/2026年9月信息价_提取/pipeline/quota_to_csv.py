"""装饰定额子目消耗量 JSON -> 两个 CSV（宽表: 子目费用; 长表: 材料消耗明细）。
用法: python quota_to_csv.py <in.json> <out_dir>
"""
import csv
import json
import sys
from pathlib import Path

inp, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)
pages = json.loads(inp.read_text(encoding="utf-8"))

FEE_COLS = ["人工费", "材料费", "机械费", "管理费", "利润", "安全文明施工措施费",
            "规费", "税金", "参考综合单价", "全费用参考综合单价"]

with open(out_dir / "子目费用宽表.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["子目编码", "章节", "计量单位", "普工人工费", "技工人 工费", "高级技工人 工费"]
               + FEE_COLS + ["勾稽通过"])
    for p in pages:
        for it in p["items"]:
            lab = it["labor"]
            w.writerow([it["code"], p["section"], p["unit"],
                        lab.get("普工", ""), lab.get("技工", ""), lab.get("高级技工", "")]
                       + [it["fees"].get(k, "") for k in FEE_COLS]
                       + ["是" if it.get("check_ok") else ""])

with open(out_dir / "材料消耗长表.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["子目编码", "章节", "子目单位", "材料名称", "规格", "单位提示",
                "消耗量", "单价", "合价"])
    for p in pages:
        for it in p["items"]:
            for m in it["materials"]:
                amt = round(m["qty"] * m["price"], 2) if m.get("price") else ""
                w.writerow([it["code"], p["section"], p["unit"], m["name"], m.get("spec", ""),
                            m.get("unit_hint", ""), m["qty"], m.get("price", ""), amt])

n_items = sum(len(p["items"]) for p in pages)
n_mats = sum(len(it["materials"]) for p in pages for it in p["items"])
print(f"宽表 {n_items} 子目 | 长表 {n_mats} 材料行 -> {out_dir}")
