# TRAE 项目规则：工程造价项目-V1

进入本仓库后，先读根目录 `TRAE_HANDOFF.md`，再读 `CODEX.md`、`docs/PROJECT_HANDOFF.md`、`AGENTS.md`。

硬规则：

1. 成本分析交付不得修改甲方原 Excel 的结构、表头、样式、公式、列序，只能在末列后追加固定 7 列：成本单价、主材、损耗率、人工、辅材、机械、合价。
2. 不要主动提交代码；不要回滚用户已有改动。
3. 不要提交 `data/cost_pricing.db`、`data/knowledge.db`、`data/exports/*.xlsx`、大 PDF。
4. ST/CT/WD/PT/MT 等编号只在当前项目内有效，不跨项目泛化。
5. 改 judge、匹配、市场价、组价逻辑后必须跑 `python app.py regression`，结果必须 `ok: true`。
6. 快速反馈用 `python app.py audit-judge --limit 500 --no-export`，正式刷新用 `python app.py audit-judge --limit 500` 和 `python app.py audit-review --top 80`。
7. 新规则必须窄口径、有 audit 或点测证据；不要为了单行硬编码包干项或项目编号价。
8. 默认不要改 `src/export/cost_analysis_template.py` 和 `src/export/inline_cost_link.py`，除非任务明确要求交付模板本身。
9. **填好价/交付的 Excel 一律放 `data/exports/`**；`清单数据资料/甲方招标清单/` 只放甲方原始文件，不得混入已填价副本。
10. **甲方招标清单格式（结构/表头/样式/公式/列序）一律不改**；价格只能填系统成本区（如 P/Q/R/S/T），其余列靠原公式联动。
11. **同表去重母行链接（强制）**：凡"项目名称+项目特征+单位"相同的条目，价格只填首次出现的**母行**，重复行对应成本列写 `=P$母行行号` 等引用公式；**母行标浅绿 `C6EFCE`、链接行标浅黄 `FFF2CC`**（系统成熟规范，见 `docs/闭环学习流程.md`）。
12. **价格闭合流程（强制）**：对甲方招标清单出分析价 → 用户回传校正后的正确价清单 → 必须做**数据分析**（逐条对比差异、按原因归类：判断口径/特征遗漏/主材规格/人工费率等，输出差距报告）→ 用金标准 `python app.py calibrate --project … --learn` 学习沉淀，实现闭环。

当前基线：

- `python app.py regression`: `ok: true`
- 六套闭环均 100%
- `audit_judge.core_main_and_labor`: `0.782`
- `audit_judge.total_cost`: `0.812`
- `auto_fill_count`: `46`

推荐下一步：按 `docs/PROJECT_HANDOFF.md` §9，从 `data/exports/待确认清单_人材机判断.xlsx` 的高风险项里挑重复、同城、同单位、非包干、非项目编号泛化的簇做窄口径优化。
