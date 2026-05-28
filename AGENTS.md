# AGENTS.md — 智能清单组价系统

> **接手本项目请先读：`docs/PROJECT_HANDOFF.md`（目的、现状、下一步、命令）。**

## 项目是什么

本地化 **工程造价知识库 + 自动组价**：学习历史 Excel 清单，对招标清单匹配填价，**保留原招标 Excel 结构**追加成本列并同表去重链接。

**实务口径**：项目名称 = 做什么；项目特征 = 施工步骤；主材多在名称里。无机涂料 = 乳胶漆（套价/匹配同乳胶漆）。

**填价链**：整项历史 → 市场参考价 → 工艺价型（慎用）→ 主材规格价。见 `src/pricing/component_judge.py`、`docs/人材机判断机制.md`。

**每次给资料**：`learn` 自动解剖 → 人材机 + 城市×档位价库 → `data/exports/解剖报告/`。

## 关键路径

| 路径 | 说明 |
|------|------|
| `docs/PROJECT_HANDOFF.md` | **交接规格（必读）** |
| `app.py` | CLI：`learn` `tender` `judge` `audit-judge` `import-catalog` |
| `src/export/inplace_bidder.py` | 原表组价导出（默认交付） |
| `src/pricing/component_judge.py` | 人材机多源判断 |
| `config/market_reference_prices.json` | 无历史时的市场参考价 |
| `config/settings.json` | 匹配阈值、auto_fill 0.8 |
| `清单数据资料/AI学习清单/` | 历史样本 |
| `清单数据资料/甲方招标清单/` | 招标样例 |

## 常用命令

```bash
pip install -r requirements.txt
python app.py init && python app.py import-catalog
python app.py relearn-all --reset
python app.py tender "招标.xlsx" --city 深圳 --tier mid --price --export
python app.py audit-judge
```

## 下一步（摘要）

见 `docs/PROJECT_HANDOFF.md` §9：补深圳信息价、多 learn 历史项目、广联达定额 OCR、audit 监控准确率。

## 修改匹配/组价时

同步更新：`config/settings.json`、`src/match/engine.py`、`src/pricing/component_judge.py`、相关 `docs/`。
