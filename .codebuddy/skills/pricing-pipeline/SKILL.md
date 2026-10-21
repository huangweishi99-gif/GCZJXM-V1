---
name: pricing-pipeline
description: 智能组价标准流程总入口。用户给新招标清单要求"按标准流程组价/跑一遍/出成本分析"时，按六阶段流水线执行：体检→格式整理→母行链接→工艺组价→复核→交付，产物分段落盘到 data/pipeline/项目目录/ 支持断点续跑；定稿确认后自动走 finalize-absorb 吸收。用户说"定稿了"时切换到 finalize-absorb 技能。
---

# 智能组价标准流程（总入口）

权威逻辑出处：仓库根 `03-cost-system-pricing-logic.md`（组价思路唯一出处，规则以它为准）。
分步细节分别由姊妹技能承担：格式=`qingdan-format-standard`，母行链接=`master-row-link`，组价=`craft-pricing`，数据库=`price-db-manage`，定稿吸收=`finalize-absorb`。本技能负责**串联与产物管理**。

## 六阶段流水线

| 阶段 | 名称 | 执行方式 | 产物（data/pipeline/<slug>/） |
|---|---|---|---|
| 1 | 清单体检 | `scripts/pricing_pipeline.py run` 自动调 `app.py validate-boq` | `01_体检报告.txt` |
| 2 | 组价导出+母行链接 | 自动调 `app.py tender <file> --price --export --dedupe-link`（系统自带去重母表+全绝对引用链接） | `02_成本分析_去重链接.xlsx` |
| 3 | 格式整理 | 自动调 `qingdan-format-standard/scripts/apply_standard_format.py`（Excel COM 保真） | 原地套打印设置 |
| 4 | 工艺组价 | **AI 按 craft-pricing 八步法执行**，先查工艺库再组价 | `03_组价工作单.csv` + `04_待确认清单.csv` |
| 5 | 复核 | **AI+用户逐行复核**，改值必须填复核依据 | `05_复核记录.csv`（**强制产物**，没有不算完） |
| 6 | 交付+定稿吸收 | 复核通过后用户说"定稿" → 切 `finalize-absorb` 一键吸收 | 交付文件 + 吸收报告 |

## 入口命令

```bash
# 新清单进流程（自动跑阶段1-3，生成4/5模板）
python .codebuddy/skills/pricing-pipeline/scripts/pricing_pipeline.py run "<招标清单.xlsx>" --city 深圳 --tier mid

# 断点续跑 / 只跑某阶段之后
python .../pricing_pipeline.py run "<文件>" --from 4

# 看进度
python .../pricing_pipeline.py status "<文件>"
```

## 阶段 4（AI 执行铁律）

1. `03_组价工作单.csv` 已由脚本**自动预填**（分部工程/名称/特征/单位/工程量/系统填价，来自导出文件）——直接在预填行上组价，不要重抄；
2. 每组一项，先 `craft_db.py query <分项名>` 查工艺工序链，再对照项目特征找缺漏/多余工序；
3. 每个单价标六级价源（定稿>期刊>定额>历史>市场参考>网查），网查价只进工作单**不进库**；
4. 特征没写的参数列入 `04_待确认清单.csv`，不得自行假设；
5. 人材机填完跑回写脚本（**禁止手工逐格改 xlsx**，也禁止 xlrd/xlwt 重写）：
   `python scripts/apply_workorder.py "data/pipeline/<项目目录>" --dry-run` 先核对，去掉 `--dry-run` 正式写；
   脚本自动按（sheet+名称+单位[+特征]）匹配定位、**跳过 L:P 为公式的链接子行**、只写母行/独立行，K 列公式自动重算。

## 阶段 5（复核铁律）

- `05_复核记录.csv` 每改一行必须填：复核值、复核依据（价源+出处）、复核人；
- 金额加权排序：优先复核偏差金额 top 行（(复核值-原值)×工程量），不因行数平均用力；
- 复核完跑 `python app.py audit-price` 数量级审计，越界项清完才可交付。

## 阶段 6

1. 交付前格式复检：`qingdan-format-standard/scripts/inspect_format.py <交付xlsx>` 逐项对照（组价/复核写过值后保险一次，COM 写值理论上不动格式）；
2. 用户说"定稿/确认了"→ 立即切 `finalize-absorb`：`absorb_final.py <定稿文件> --id <项目代号> --city <城市> --tier <档位>`，零回归才算闭环。

## 红线汇总（全流程通用）

- 交付文件一律 Excel COM 保真写入；母行链接全绝对引用（lj 语义）；
- LLM 拍价禁止入库，无价源宁留空标待询价；
- `05_复核记录.csv` 缺失 = 流程未走完，不得交付；
- 整项单位（项/系统/宗）不进单价聚合（包干价不构成可比单价）。
