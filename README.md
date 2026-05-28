# 智能清单组价系统

自主学习历史清单成本 → 对甲方招标清单 **精确/模糊** 匹配相同项 → 导出 **投标方 18 列单价分析表**（含 Excel 公式）。

**GitHub 仓库**：https://github.com/huangweishi99-gif/GCZJXM-V1  

**接手开发 / 其他模型**：请先读 [`docs/PROJECT_HANDOFF.md`](docs/PROJECT_HANDOFF.md) 与 [`AGENTS.md`](AGENTS.md)。

## 安装（Python 环境，无需 Cursor 扩展）

```powershell
cd "c:\Users\guangwan\Documents\工程造价项目-V1"
pip install -r requirements.txt
python app.py init
```

| 组件 | 说明 |
|------|------|
| Python 3.11+ | 必须 |
| `rapidfuzz` | 模糊匹配 |
| `streamlit` | 图形界面（可选） |
| Excel | 仅编辑导出文件时需要 |

**Cursor 协作**：见 `.cursor/rules/工程造价组价.mdc`、`AGENTS.md`

## 命令行

```powershell
# 学习入库（每次自动解剖：人材机拆分 + 城市×档位价库 + 解剖报告）
python app.py relearn-all --reset   # 批量学习 AI学习清单 全部项目（推荐首次或库混乱时）

python app.py learn "清单数据资料/AI学习清单/某项目.xlsx" --city 深圳 --tier mid
python app.py backfill-kb           # 老库回填城市/档位并重建价库

# 招标组价（匹配模式：auto / exact / fuzzy）
python app.py tender "招标清单.xlsx" --price --export

# 导出：在原招标 Excel 上追加成本列、填价、同表去重链接（默认 data/exports/原名_组价.xlsx）
# 另存独立模板表（可选）：
python app.py tender "招标清单.xlsx" --price --export --dedupe-link

# 仅去重（不组价）
python app.py dedupe "招标清单.xlsx"

# 母表填价后链接全量清单
python app.py link-price "招标清单.xlsx" --master "去重母表_xxx.xlsx"

# 测试匹配
python app.py match "轻钢龙骨隔墙（100mm）" --unit "㎡" --feature "100mm"

python app.py import-catalog          # 主材辅材判定表 → 知识库
python app.py judge "项目名称" --feature "特征" --unit ㎡ --city 深圳 --tier mid
python app.py audit-judge             # 回测人材机判断准确率

python app.py stats
```

克隆后若无 `data/cost_pricing.db`，请执行：`python app.py relearn-all --reset` 与 `python app.py import-catalog`。

## 图形界面

```powershell
streamlit run ui.py
```

## 匹配模式

| 模式 | 说明 |
|------|------|
| `exact` | 名称≥98%、特征≥92%、工艺/标签≥95%，只自动填 A 级 |
| `fuzzy` | 允许模糊，A/B 级自动填价；**特征工艺对不上不填** |
| `auto` | 默认：先精确，再模糊 |

**组价原则**：项目特征每一条对应一道施工工艺，不能只看项目名称套价。

## 文档

- **`docs/PROJECT_HANDOFF.md`**（项目交接 / 下一步）
- `docs/知识库解剖流程.md`（**每次给资料的标准流程**）
- `docs/清单定额与组价原理.md` · `docs/人材机判断机制.md`
- `docs/项目特征与施工工艺.md` · `docs/主材与辅材识别原则.md`
- `docs/装饰工程施工工艺与定额套用.md`

- `docs/需求与实施计划-智能清单组价系统.md`
- `docs/表头对照与计算公式.md`
- `docs/lj链接程序解读与融合方案.md`
