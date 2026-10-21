"""信息价CSV -> market_reference_prices.json 候选规则生成器。
输出: 2026年9月信息价_提取/market_ref_candidates_202609.json
- 只生成候选，不直接合并进 config；与现有规则 name_keywords 冲突的标记 conflict
- 单位缺失的按名称关键词推断, source_note 标注[单位推断]
"""
import csv
import json
import re
from pathlib import Path

WORK = Path(r"d:\projects\cost-estimation\清单数据资料\AI学习清单\广联达定额\2026年9月信息价_提取")
CSV = WORK / "2026年9月深圳信息价.csv"
EXISTING = Path(r"d:\projects\cost-estimation\config\market_reference_prices.json")
OUT = WORK / "market_ref_candidates_202609.json"

# ---- 单位推断: 名称关键词 -> 单位 ----
UNIT_GUESS = [
    (("钢筋", "钢材", "钢管", "钢板", "水泥", "混凝土", "砂浆", "沥青", " gasoline", "柴油", "汽油", "电解铜", "铝锭", "锌锭"), "t"),
    (("管材", "电线", "电缆", "线槽", "线管", "桥架", "型材", "栏杆", "扶手", "PPR", "PVC", "PE管", "镀锌", "角钢", "槽钢", "方钢", "圆钢"), "m"),
    (("玻璃", "石材", "砖", "瓷砖", "瓦", "卷材", "石膏板", "铝板", "钢板网", "饰面板", "免漆板", "模板"), "㎡"),
    (("砂石", "碎石", "砌块", "毛石", "土"), "m³"),
    (("油漆", "涂料", "乳胶漆", "防水", "胶粘剂", "胶水", "砂浆王"), "kg"),
    (("苗木", "乔木", "灌木"), "株"),
    (("花卉", "草坪"), "㎡"),
]

def guess_unit(name, price):
    for kws, u in UNIT_GUESS:
        if any(k in name for k in kws):
            return u
    if any(k in name for k in ("给水管", "排水管", "水管", "井管", "穿线管", "波纹管", "螺旋管")):
        return "m"
    return ""

RE_COL = re.compile(r"^[\d·．]+(臂长|安装|标准|为)")

def clean_name(name):
    return name.replace("巧", "15").replace("咼", "").strip()

def clean_unit(unit, name):
    u = unit.replace("巧", "15").replace("（", "(").replace("）", ")")
    if "月" in u and any(k in name for k in ("起重机", "电梯", "井架", "脚手架", "泵")):
        return "台·月"
    if re.search(r"^[·．.）)]*月$", u):
        return "台·月"
    return u

def clean_spec(spec, name):
    s = spec.replace("小", "φ")
    if s and s[0].isdigit() and any(k in name for k in ("钢筋", "圆钢", "线材", "盘螺")):
        s = "φ" + s
    return s

existing_rules = json.loads(EXISTING.read_text(encoding="utf-8"))["rules"]
existing_names = set()
for r in existing_rules:
    existing_names.update(r.get("name_keywords", []))

rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
cands, conflicts, skipped = [], [], 0
for r in rows:
    if r["有效"] != "是" or not r["价格"]:
        skipped += 1
        continue
    name = clean_name(r["材料名称"])
    spec = clean_spec(r["规格"].strip(), name)
    unit = clean_unit(r["单位"].strip(), name)
    if len(name) < 3 or not re.search(r"[一-鿿]", name):
        skipped += 1
        continue
    try:
        price = float(r["价格"])
    except ValueError:
        skipped += 1
        continue
    if price <= 0:
        skipped += 1
        continue
    if not unit:
        unit = guess_unit(name, price)
        unit_note = "[单位推断]" if unit else "[单位缺失]"
    else:
        unit_note = ""
    rule = {
        "id": f"sz202609_p{r['页']}_{r['序号'] or len(cands)}",
        "name_keywords": [name],
        "units": [unit] if unit else [],
        "material_main": price,
        "material_aux": 0,
        "labor": 0,
        "machinery": 0,
        "material_loss_rate": 0.0,
        "cities": ["深圳"],
        "confidence": 0.7,
        "source_note": f"深圳信息价2026.9 p{r['页']} {unit_note} 原名:{name} {spec}",
    }
    if spec:
        rule["feature_keywords"] = [spec]
        rule["require_feature_keywords"] = True
    if name in existing_names:
        conflicts.append(rule)
    else:
        cands.append(rule)

doc = {
    "_comment": "深圳建设工程价格信息2026年9月 -> market_reference 候选. 人工审后可用 merge 脚本并入 config/market_reference_prices.json",
    "_stats": {"候选": len(cands), "与现有规则冲突": len(conflicts), "跳过": skipped},
    "candidates": cands,
    "conflicts": conflicts,
}
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"候选 {len(cands)} | 冲突 {len(conflicts)} | 跳过 {skipped} -> {OUT.name}")
print()
for r in cands[:6] + cands[200:204] + cands[-4:]:
    print(f"  {r['id']:22} {r['name_keywords'][0][:16]:16} {r.get('feature_keywords', [''])[0][:12]:12} "
          f"{r['units']} {r['material_main']:>10} {r['source_note'][-30:]}")
