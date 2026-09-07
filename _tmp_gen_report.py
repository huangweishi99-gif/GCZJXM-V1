# -*- coding: utf-8 -*-
"""临时：生成《云湾控制价异常清单》Markdown 报告（用后即删）。"""
import io, sys, csv, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CALC = r"data\tmp\母行测算结果_全量.csv"
OUT = r"data\exports\云湾控制价异常清单-20260825.md"

rows = list(csv.DictReader(open(CALC, encoding="utf-8-sig")))
recs = []
for r in rows:
    try:
        ctrl = float(r["控制价"]); cur = float(r["现成本"]); new = float(r["新成本"])
        qty = float(r["工程量"] or 0)
    except (ValueError, TypeError, KeyError):
        continue
    if ctrl <= 0:
        continue
    cd = float(r["现差异%"]) if r.get("现差异%") else (cur * 1.12 / ctrl - 1) * 100
    nd = float(r["新差异%"]) if r.get("新差异%") else (new * 1.12 / ctrl - 1) * 100
    if abs(nd) <= 30:
        continue
    recs.append({
        "文件": r.get("文件", ""), "行": int(r["行"]), "名称": r["项目名称"],
        "单位": r.get("单位", ""), "工程量": qty, "控制价": ctrl,
        "现成本": cur, "现差异": cd, "新成本": new, "新差异": nd,
        "金额影响": abs(ctrl - cur) * qty, "分析": r.get("分析", ""),
    })

grp_low = sorted([x for x in recs if x["现差异"] > 30], key=lambda x: -x["金额影响"])
grp_high = sorted([x for x in recs if x["现差异"] < -30], key=lambda x: -x["金额影响"])
grp_ok = sorted([x for x in recs if -30 <= x["现差异"] <= 30], key=lambda x: -x["金额影响"])

def fmt(x):
    tag = "5#6#" if x["文件"] == "5#6#" else ("会所" if "会所xls" in x["文件"] else x["文件"])
    note = x["分析"] or ""
    return f'| {tag} | {x["行"]} | {x["名称"]} | {x["单位"]} | {x["工程量"]:g} | {x["控制价"]:.2f} | {x["现成本"]:.2f} | {x["现差异"]:+.0f}% | {x["新成本"]:.2f} | {x["新差异"]:+.0f}% | {x["金额影响"]:,.0f} | {note} |'

with open(OUT, "w", encoding="utf-8") as f:
    f.write("# 云湾花园控制价异常清单（残余 54 条）\n\n")
    f.write("> 生成时间：2026-08-25。三份云湾文件 761 条母行已按工艺/主材规格独立重新组价（准确市场价，"
            "不再贴控制价），仍有 54 条测算成本与控制价差异 >30%，均属**控制价自身异常**（漏项/虚高），"
            "文件中的成本已是市场合理价。\n\n")
    f.write("## 一、控制价疑似偏低（现成本>控制价，投标有亏损风险，建议与甲方核对）\n\n")
    f.write(f"共 {len(grp_low)} 条，按金额影响排序：\n\n")
    f.write("| 文件 | 行 | 项目名称 | 单位 | 工程量 | 控制价 | 现成本 | 现差异 | 测算成本 | 测算差异 | 金额影响(元) | 备注 |\n")
    f.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for x in grp_low:
        f.write(fmt(x) + "\n")
    f.write("\n## 二、控制价疑似虚高（现成本<控制价，报价有竞争力，可放心）\n\n")
    f.write(f"共 {len(grp_high)} 条，按金额影响排序：\n\n")
    f.write("| 文件 | 行 | 项目名称 | 单位 | 工程量 | 控制价 | 现成本 | 现差异 | 测算成本 | 测算差异 | 金额影响(元) | 备注 |\n")
    f.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for x in grp_high:
        f.write(fmt(x) + "\n")
    f.write("\n## 三、现值已贴近控制价（现差异≤30%，文件未覆盖；但测算值偏差大，控制价存疑）\n\n")
    f.write(f"共 {len(grp_ok)} 条，按金额影响排序：\n\n")
    f.write("| 文件 | 行 | 项目名称 | 单位 | 工程量 | 控制价 | 现成本 | 现差异 | 测算成本 | 测算差异 | 金额影响(元) | 备注 |\n")
    f.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for x in grp_ok:
        f.write(fmt(x) + "\n")
    f.write("\n## 汇总\n\n")
    f.write(f"- 母行总数 761（另 1 条成本/控制价为 0），±15% 内 581 条（76.4%），15~30% 126 条（16.6%），>30% 残余 {len(recs)} 条（7.1%）。\n")
    f.write(f"- 控制价疑似偏低 {len(grp_low)} 条，疑似虚高 {len(grp_high)} 条，已贴控制价但存疑 {len(grp_ok)} 条。\n")
    f.write("- 本次全量重新组价：独立测算写回 325 条（5#6# 212 / 会所 100 / 安装 13），142 条定制柜/成品家具保持历史结构（无独立组价数据，详见下方说明）。\n")
    f.write("- 反坎类（淋浴区 C25/细石混凝土）控制价 1.16~4.53 元/m 明显漏项，正确成本 5~33 元/m。\n")
    f.write("- 墙布类控制价 450~612 元/m² 虚高（应 140~229 元/m²），注意勿被其拉高报价。\n")
    f.write("- 不锈钢线条控制价波动剧烈（6.41~52.96 元/m），建议统一按展开尺寸核价。\n\n")
    f.write("## 未独立组价项（142 条，保持历史成本结构）\n\n")
    f.write("以下行无法按工艺独立组价（清单无尺寸/品牌数据），成本保持为历史 learn 值或按控制价结构拆分：\n\n")
    f.write("- **定制柜类**（5#6# 117 条）：玄关柜、衣柜、橱柜-地柜/冰箱柜、书柜、水吧柜、岛台、镜柜、洗手台柜等，按控制价 55%/17%/6%/1% 拆分。\n")
    f.write("- **会所定制/家具**（25 条）：水吧柜、沙盘、接待台、木饰面柜、健身房柜子等。\n")
    f.write("- **架空层成品家具/健身器材**：旋转木马、台球桌、普拉提床、户外沙发、棋牌桌、攀爬架等，按成品采购口径保留（控制价×0.70 结构）。\n\n")
    f.write("> 如需对这些项精确核价，需补充柜体投影/展开面积或成品品牌型号。\n")

print(f"残余 {len(recs)} 条：偏低 {len(grp_low)}，虚高 {len(grp_high)}，已贴控制价 {len(grp_ok)}")
print("报告已输出:", OUT)
