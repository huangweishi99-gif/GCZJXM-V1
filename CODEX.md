# Codex 一键接手

> **新 Agent 只读本文 + `docs/PROJECT_HANDOFF.md` 即可开工。**  
> 详细规格、铁律、完成度、下一步见 [`docs/PROJECT_HANDOFF.md`](docs/PROJECT_HANDOFF.md)。
> 国内 TRAE IDE 接手见 [`TRAE_HANDOFF.md`](TRAE_HANDOFF.md)。

---

## 30 秒理解

| 项 | 内容 |
|----|------|
| **是什么** | 本地化工程造价知识库 + 自动组价：学历史 Excel，对招标清单填价，**原表不动**、末列后追加统一成本区 |
| **主交付** | `python app.py deliver --project <id>` → `inline_cost_link` + `cost_analysis_template` |
| **金标准** | 七套闭环项目校准 **100%（±10%）**；`audit-judge` 全量核心准确 **72.8%**（目标 80%） |
| **当前阶段** | 交付链已稳定；已加 **价格数量级防线 / 定额量价分离 / 取费库 / 清单五要素体检**；主攻 **待确认清单复核、压低 unresolved/generic_finish、learn 更多历史、精化 MEP/市场价** |

---

## 5 分钟环境恢复

```powershell
cd "c:\Users\guangwan\Documents\工程造价项目-V1"
pip install -r requirements.txt
python app.py init
python app.py import-catalog
python app.py relearn-all          # 无库或换机时加 --reset
python app.py regression           # 必须全绿再继续改 judge/匹配
```

**验收标准**：`regression_summary.json` → `"ok": true`，六项目 `within_10pct` 均为 100%。

---

## 三条铁律（违反即返工）

1. **甲方招标表**：数据、表头、样式、列序 **一律不改**；只在甲方末列后 **空 1 列** 起追加 7 列成本区（见 `cost_analysis_template.py`）。
2. **组价口径**：名称 = 做什么；特征 = 施工步骤；**名称+特征+单位** 都相似才强套历史；ST/CT/WD 等编号 **仅该项目** 有效。
3. **改 judge/匹配后**：必跑 `python app.py regression`；新 Excel 必 `learn`，不能只改内存规则。

---

## 改代码前先打开

| 任务 | 文件 |
|------|------|
| 交付/成本列/公式桥接 | `src/export/cost_analysis_template.py` |
| 填价入口 | `src/export/inline_cost_link.py` |
| 人材机判断 | `src/pricing/component_judge.py` |
| 表头识别 | `src/ingest/detector.py`（禁止写死列号） |
| 闭环配对 | `config/project_pairs.json` |
| 阈值 | `config/settings.json` |
| 市场价 | `config/market_reference_prices.json` |
| 工艺桶 | `config/craft_trade_rules.json` |

---

## 接手后第一件事（推荐）

```powershell
python app.py regression
python app.py audit-judge --limit 500
python app.py audit-review --top 80
```

读 `data/exports/regression_summary.json`、`audit_judge_summary.json` 与 `待确认清单_人材机判断.xlsx`，再按 `PROJECT_HANDOFF.md` §9 优先级改。

---

## 不要做的事

- 不要给每个甲方清单写死列号（用 `detect_connection_profile`）
- 不要跨项目通用 ST/CT/WD 编号价
- 不要未经 regression 就放宽 `auto_fill`
- 不要提交 `data/cost_pricing.db`、大 PDF、`data/exports/*.xlsx`（见 `.gitignore`）
- 用户未要求时不要 `git commit`

---

*与 `AGENTS.md`、`docs/PROJECT_HANDOFF.md` 同步维护。*
