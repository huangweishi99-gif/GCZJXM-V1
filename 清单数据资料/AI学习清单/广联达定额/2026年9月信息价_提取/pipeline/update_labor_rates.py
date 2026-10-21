"""深圳定额工日价格(2026.9) -> config/labor_rates.json 对照更新。
口径决策:
- 直接对齐: 普工/技工/装饰技工(取中档)/新增高级技工/新增安装工
- labor_unit_price 保持与技工的镜像关系
- 不动: 木工/油工/瓦工/电工/水暖工/焊工(信息价无对应工种, 不拍价)
- 不动: machinery_unit_price(130是综合台班价口径, 信息价177.57只是机上人工)
"""
import json
import shutil
from pathlib import Path

TARGET = Path(r"d:\projects\cost-estimation\config\labor_rates.json")
bak = TARGET.with_suffix(".json.bak_202609")
shutil.copy2(TARGET, bak)

d = json.loads(TARGET.read_text(encoding="utf-8"))
sz = d["cities"]["深圳"]
t = sz["trades"]

changes = [
    ("普工", 280, 153, "普通工日 152.56"),
    ("技工", 350, 186, "技术工日 186.03"),
    ("装饰技工", 380, 232, "装饰工日2 231.95(中档)"),
    ("安装工", None, 212, "安装工日 212.02(新增)"),
    ("高级技工", None, 256, "高级技术工日 256.12(新增)"),
]
for name, old, new, src in changes:
    if old is None:
        print(f"  + {name}: (无) -> {new}  [{src}]")
    else:
        print(f"  ~ {name}: {old} -> {new}  [{src}]")
    t[name] = new

sz["labor_unit_price"] = t["技工"]
print(f"  ~ labor_unit_price: 350 -> {sz['labor_unit_price']}  [保持=技工]")
print("  = machinery_unit_price: 130 不动  [综合台班价口径 != 机上人工177.57]")
print("  = 木工/油工/瓦工/电工/水暖工/焊工 不动  [信息价无对应工种, 不拍价]")

d["version"] = "2026.09"
note = ("2026.09起深圳工种单价=造价站定额工日价格口径(信息价月刊); "
        "细分工种(木/油/瓦/电/水暖/焊)沿用2026.08市场口径, 待官方细分发布再对齐")
d.setdefault("说明", "")
if note not in d["说明"]:
    d["说明"] = (d["说明"] + " " + note).strip()

TARGET.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n已写入, 备份 -> {bak.name}")
