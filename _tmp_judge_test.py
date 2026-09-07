# -*- coding: utf-8 -*-
"""临时：测试系统 judge_line_components 对云湾差异大母行的测算质量（用后即删）。"""
import io, sys, os, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.query import PricingContext
from src.pricing.engine import PricingEngine
from src.pricing.component_judge import judge_line_components
import win32com.client

XLS_A = r"清单数据资料\甲方招标清单\云湾花园项目-5#6#户内、公区，样板，架空层装修工程专业分包-投标清单-20260825.xls"

rows = list(csv.DictReader(open(r"data\tmp\母行差异分析.csv", encoding="utf-8-sig")))
bad = [r for r in rows if r["类型"] == "母行" and r["文件"] == "5#6#" and
       r["差异%"] not in (None, "") and abs(float(r["差异%"])) > 30]
print(f"差异>30% 母行 {len(bad)} 个")

# 按差异绝对值降序取 12 个代表
bad_sorted = sorted(bad, key=lambda r: -abs(float(r["差异%"])))
samples = bad_sorted[:12]

xl = win32com.client.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
wb = xl.Workbooks.Open(os.path.abspath(XLS_A), UpdateLinks=0, ReadOnly=True)
ws = wb.Worksheets("清单表")

repo = KnowledgeRepository(None)
engine = PricingEngine(None)
for city in ("珠海", "深圳"):
    ctx = PricingContext(city=city, price_tier="mid")
    print(f"\n========== city={city} ==========")
    for r in samples:
        row = int(r["行"])
        name = str(ws.Cells(row, 2).Value or "")
        feature = str(ws.Cells(row, 3).Value or "")
        unit = str(ws.Cells(row, 6).Value or "")
        j = judge_line_components(name, feature, unit, engine, repo, ctx=ctx)
        print(f"行{row} | {name[:20]} | {unit} | 控制价{r['控制价']:>9} 现成本{r['成本']:>9} 差异{r['差异%']}%")
        print(f"   -> 源={j.source} 置信={j.confidence:.2f} auto={j.auto_fill_ok} "
              f"主材={j.material_main:.2f} 人工={j.labor:.2f} 辅材={j.material_aux:.2f} 机械={j.machinery:.2f} 损耗={j.material_loss_rate:.3f} 合计={j.cost_unit_price:.2f}")
wb.Close(False)
xl.Quit()
