"""把 market_ref 候选合并进 config/market_reference_prices.json。
用法: python merge_market_ref.py          # dry-run，只打印计划
      python merge_market_ref.py --apply   # 真正写入（先备份 .bak）
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(r"d:\projects\cost-estimation")
CANDS = ROOT / "清单数据资料" / "AI学习清单" / "广联达定额" / "2026年9月信息价_提取" / "market_ref_candidates_202609.json"
TARGET = ROOT / "config" / "market_reference_prices.json"

doc = json.loads(CANDS.read_text(encoding="utf-8"))
cands = doc["candidates"]
conflicts = doc["conflicts"]

target = json.loads(TARGET.read_text(encoding="utf-8"))
existing_ids = {r["id"] for r in target["rules"]}
existing_names = set()
for r in target["rules"]:
    existing_names.update(r.get("name_keywords", []))

fresh, dup_id, dup_name = [], 0, 0
for r in cands:
    if r["id"] in existing_ids:
        dup_id += 1
        continue
    if any(k in existing_names for k in r["name_keywords"]):
        dup_name += 1
        continue
    fresh.append(r)

print(f"候选 {len(cands)} | 冲突区 {len(conflicts)}（不入）")
print(f"新增 {len(fresh)} | id重复 {dup_id} | 关键词与现有规则重复 {dup_name}")
print(f"合并后规则总数: {len(target['rules'])} -> {len(target['rules']) + len(fresh)}")

if "--apply" not in sys.argv:
    print("\n[dry-run] 加 --apply 才真正写入")
    sys.exit(0)

bak = TARGET.with_suffix(".json.bak_202609")
shutil.copy2(TARGET, bak)
target["rules"].extend(fresh)
TARGET.write_text(json.dumps(target, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n[apply] 已写入 {len(fresh)} 条，备份 -> {bak.name}")
print("提醒: 合并后跑 python app.py regression 确认无回归")
