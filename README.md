# 智能清单组价系统

自主学习历史清单成本 → 对甲方招标清单 **精确/模糊** 匹配相同项 → 导出 **投标方 18 列单价分析表**（含 Excel 公式）。

**GitHub 仓库**：https://github.com/huangweishi99-gif/GCZJXM-V1

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
# 学习入库
python app.py relearn-all --reset   # 批量学习 AI学习清单 全部项目（推荐首次或库混乱时）

python app.py learn "清单数据资料/AI学习清单/某项目.xlsx"

# 招标组价（匹配模式：auto / exact / fuzzy）
python app.py tender "招标清单.xlsx" --price --export --match-mode auto

# 大清单推荐：去重链接导出（相同项只填母表一次）
python app.py tender "招标清单.xlsx" --price --export --dedupe-link

# 仅去重（不组价）
python app.py dedupe "招标清单.xlsx"

# 母表填价后链接全量清单
python app.py link-price "招标清单.xlsx" --master "去重母表_xxx.xlsx"

# 测试匹配
python app.py match "轻钢龙骨隔墙（100mm）" --unit "㎡" --feature "100mm"

python app.py stats
```

## 图形界面

```powershell
streamlit run ui.py
```

## 匹配模式

| 模式 | 说明 |
|------|------|
| `exact` | 仅名称≥98%、特征≥92%，只自动填 A 级 |
| `fuzzy` | 允许模糊，A/B 级自动填价 |
| `auto` | 默认：先精确，再模糊 |

## 文档

- `docs/需求与实施计划-智能清单组价系统.md`
- `docs/表头对照与计算公式.md`
- `docs/lj链接程序解读与融合方案.md`
