# AGENTS.md — 智能清单组价系统

## 项目是什么

本地化 **工程造价知识库 + 自动组价**：学习历史 Excel 清单，对招标清单做精确/模糊匹配，导出投标方单价分析表。

## 关键路径

| 路径 | 说明 |
|------|------|
| `app.py` | CLI 入口 |
| `ui.py` | Streamlit 图形界面 |
| `src/ingest/` | 表头识别、解析 |
| `src/match/` | 相同项精确/模糊匹配 |
| `src/knowledge/` | 入库 learn |
| `src/pricing/` | 组价 |
| `src/export/` | Excel 导出 |
| `config/settings.json` | 阈值、匹配模式、费率 |
| `清单数据资料/AI学习清单/` | 用户样本 |

## 常用命令

```bash
pip install -r requirements.txt
python app.py init
python app.py learn "清单数据资料/AI学习清单/xxx.xlsx"
python app.py tender "招标.xlsx" --price --export --match-mode auto
python app.py match "项目名称" --feature "特征" --unit "㎡"
streamlit run ui.py
```

## 修改匹配逻辑时

同时更新：`config/settings.json`、`src/match/engine.py`、`docs/需求与实施计划-智能清单组价系统.md`。
