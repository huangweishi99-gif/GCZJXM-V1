# TRAE IDE 一键接手

> 给国内 TRAE IDE / TRAE AI 助手使用。打开本仓库后，先读本文，再读 `CODEX.md` 和 `docs/PROJECT_HANDOFF.md`。

## 一键接手提示词

把下面这段发给 TRAE AI：

```text
你现在接手本地工程造价项目：C:\Users\guangwan\Documents\工程造价项目-V1。

请严格按以下顺序工作：
1. 先读 TRAE_HANDOFF.md、CODEX.md、docs/PROJECT_HANDOFF.md、AGENTS.md。
2. 不要改动甲方 Excel 原表结构、表头、样式、公式和列序；成本分析只能在末列后追加固定 7 列：成本单价、主材、损耗率、人工、辅材、机械、合价。
3. 改 judge、匹配、市场价、组价逻辑前后都要跑 python app.py regression；回归必须 ok: true。
4. 优先用 python app.py audit-judge --limit 500 --no-export 做快速反馈，再用 audit-review 看高风险清单。
5. 只做窄口径、可验证的改动；不要跨项目泛化 ST/CT/WD/PT/MT 等物料编号。
6. 不要主动 git commit；不要提交 data/cost_pricing.db、data/exports/*.xlsx、大 PDF。
7. 修改交付链前必须先说明原因；默认不要碰 src/export/cost_analysis_template.py 和 src/export/inline_cost_link.py。

接手后先汇报当前 regression/audit 状态，然后按 docs/PROJECT_HANDOFF.md §9 的 ROI 优先级继续推进。
```

## 30 秒理解项目

这是一个本地化工程造价知识库 + 自动组价系统：

- 从历史 Excel 清单学习人材机成本拆解，写入本地 SQLite。
- 对甲方招标清单按「项目名称 + 项目特征 + 单位 + 城市档位」匹配填价。
- 交付时保留甲方原 Excel 结构，只追加统一成本分析区，并做同表去重链接。
- 主入口：`python app.py deliver --project <project_id>`。
- 核心判断：`src/pricing/component_judge.py`。
- 主交付链：`src/export/inline_cost_link.py` + `src/export/cost_analysis_template.py`。

## Windows 环境恢复

在 TRAE 终端用 PowerShell：

```powershell
cd "C:\Users\guangwan\Documents\工程造价项目-V1"
$env:PYTHONIOENCODING="utf-8"
pip install -r requirements.txt
python app.py init
python app.py import-catalog
```

如果是新机器或数据库缺失，再执行：

```powershell
python app.py relearn-all --reset
```

如果本机已有 `data/cost_pricing.db`，不要随便重建；先跑验证。

## 接手后第一组命令

```powershell
$env:PYTHONIOENCODING="utf-8"
python app.py regression
python app.py audit-judge --limit 500
python app.py audit-review --top 80
```

通过标准：

- `data/exports/regression_summary.json` 中 `"ok": true`。
- 六个闭环项目 `within_10pct` 都是 100%。
- `audit_judge_summary.json` 里 `core_main_and_labor` 不低于当前基线。
- `audit-review` 正常生成 `data/exports/待确认清单_人材机判断.xlsx`。

当前已知基线：

- regression: `ok: true`
- 六套闭环：`166/166`、`78/78`、`387/387`、`55/55`、`75/75`、`160/160`
- audit samples: `500`
- `core_main_and_labor`: `0.782`
- `total_cost`: `0.812`
- `auto_fill_count`: `46`
- `auto_fill_rate`: `0.092`
- `market_reference` 高风险 review 行：`27`

## 成本分析交付铁律

甲方表格式可以不同，但成本分析格式永远相同。

严禁：

- 改甲方原表头、样式、合并单元格、公式、列序。
- 给某个项目写死列号。
- 把甲方原公式改成死数。

只能：

- 在甲方最后一列后空 1 列。
- 追加固定 7 列，顺序不可变：

```text
成本单价 | 主材 | 损耗率 | 人工 | 辅材 | 机械 | 合价
```

公式口径：

```text
成本单价 = 主材 + 主材 × 损耗率 + 人工 + 辅材 + 机械
合价 = 成本单价 × 工程量
```

连接画像只在 `src/export/cost_analysis_template.py` 维护：

- `haide_inquiry`
- `tender_breakdown`
- `national_quote`

## 改 judge / 匹配的硬流程

任何涉及以下文件的改动，都按硬流程走：

- `src/pricing/component_judge.py`
- `src/pricing/market_reference.py`
- `src/pricing/mep_install_price.py`
- `src/pricing/special_line_price.py`
- `src/match/engine.py`
- `config/market_reference_prices.json`
- `config/settings.json`
- `config/craft_trade_rules.json`

流程：

```powershell
$env:PYTHONIOENCODING="utf-8"
python app.py regression

# 做窄口径修改

python -m json.tool config\market_reference_prices.json > $null
python app.py audit-judge --limit 500 --no-export
python app.py regression
python app.py audit-judge --limit 500
python app.py audit-review --top 80
```

完成条件：

- regression 仍为 `ok: true`。
- 六套闭环仍全 100%。
- `auto_fill_count` 不应无依据扩张。
- 目标行要用点测或 audit 明细证明改善。
- 同步更新相关文档，至少是 `docs/PROJECT_HANDOFF.md` 的已知坑或 §9 状态。

## 当前优化方向

按 `docs/PROJECT_HANDOFF.md` §9 继续，优先级如下：

1. P0：处理 `audit-review` 高风险前 20 行。
2. P0：learn 未入库历史清单，提高强历史匹配占比。
3. P1：从金标准提炼 `zh_` / `sz_` 城市市场价。
4. P1：继续压低 `generic_finish`、`unresolved`。
5. P1：继续细化 MEP、电缆、冷媒、CL 灯槽/边槽等专项价型。
6. P2：把 regression 后自动 audit 做成门禁。
7. P2：广联达定额 OCR。

当前推荐下一步：

- 从最新 `data/exports/待确认清单_人材机判断.xlsx` 里挑重复、同城、同单位、非包干、非项目编号泛化的高风险簇。
- 优先 `market_reference` 剩余高风险行，但不要硬编码项目编号价。

## 近期关键修正

- `MarketRef.preserve_components`：已有可信分项拆分的市场参考价不再按工艺模板二次拆分。
- `putty_hang_waterproof`：挂耐水腻子保留 `7.6 / 7.2 / 3.8 / 0.38`，目标行 `1271`、`1463` 在正式抽检报告中 `core=True`、`strict=True`、`auto=False`。
- 电缆规格解析：名称里有明确线缆型号时优先用名称规格，避免特征里的通用 `规格:2.5` 覆盖或重复累计。

## 常用命令

```powershell
# 单项判断
python app.py judge "墙面挂耐水腻子" --unit "㎡" --city 深圳 --tier mid

# 招标交付
python app.py deliver --project haide_sales
python app.py deliver --project haide_club_merge

# 校准并固化学习
python app.py calibrate --project haide_sales --learn

# 新资料学习
python app.py learn "清单数据资料/AI学习清单/某项目.xlsx" --city 珠海 --tier mid

# 手机同步
python app.py sync serve
python app.py sync token --show
python app.py sync bundle
python app.py sync pull
```

## 文件速查

| 任务 | 文件 |
|------|------|
| CLI 入口 | `app.py` |
| 完整交接规格 | `docs/PROJECT_HANDOFF.md` |
| Codex 一键接手 | `CODEX.md` |
| Agent 规则 | `AGENTS.md` |
| 成本分析模板 | `src/export/cost_analysis_template.py` |
| 交付入口 | `src/export/inline_cost_link.py` |
| 人材机判断 | `src/pricing/component_judge.py` |
| 市场参考价 | `config/market_reference_prices.json` |
| 市场价匹配 | `src/pricing/market_reference.py` |
| MEP 专项价型 | `src/pricing/mep_install_price.py` |
| 特殊零散项 | `src/pricing/special_line_price.py` |
| 闭环项目配对 | `config/project_pairs.json` |
| 阈值 | `config/settings.json` |
| 审计复核 | `src/pricing/audit_review.py` |
| 手机同步服务 | `src/sync/api.py` |

## 不要做

- 不要主动 `git commit`。
- 不要 `git reset --hard`、不要回滚用户已有改动。
- 不要提交 `data/cost_pricing.db`、`data/knowledge.db`、`data/exports/*.xlsx`。
- 不要跨项目通用 ST/CT/WD/PT/MT 编号。
- 不要未经 regression 放宽 `auto_fill`。
- 不要为了单个 Excel 写死列号。
- 不要把成本分析模板改成每个项目一套逻辑。

## 给 TRAE 的完成汇报格式

每次完成一轮，按这个格式回复：

```text
本轮改动：
- ...

验证：
- python app.py audit-judge --limit 500 --no-export: ...
- python app.py regression: ok: true / 失败原因
- python app.py audit-review --top 80: ...

指标变化：
- core_main_and_labor: x -> y
- market_reference/core 或目标 source: x -> y
- auto_fill_count: x -> y

风险：
- ...

下一步：
- ...
```

