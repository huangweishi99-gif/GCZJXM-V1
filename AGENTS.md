# AGENTS.md — 智能清单组价系统

> **Codex / 新 Agent 一键接手：先读 [`CODEX.md`](CODEX.md)（5 分钟），再读 [`docs/PROJECT_HANDOFF.md`](docs/PROJECT_HANDOFF.md)（完整规格）。**

## 项目是什么

本地化 **工程造价知识库 + 自动组价**：学习历史 Excel 清单，对招标清单匹配填价，**保留原招标 Excel 结构**追加成本列并同表去重链接。

**实务口径**：项目名称 = 做什么；项目特征 = 施工步骤；主材多在名称里。无机涂料 = 乳胶漆（套价/匹配同乳胶漆）。

**填价链**：整项历史 → 市场参考价 → 工艺价型（慎用）→ 主材规格价。见 `src/pricing/component_judge.py`、`docs/人材机判断机制.md`。

**ST/CT/WD 等编号**：仅为**该项目**物料书代号，不跨项目通用；见 `docs/项目石材与主材编号价库.md`。

**每次给资料**：`learn` 自动解剖 → 人材机 + 城市×档位价库 → `data/exports/解剖报告/`。

## 关键路径

| 路径 | 说明 |
|------|------|
| `CODEX.md` | **一键接手（5 分钟）** |
| `docs/PROJECT_HANDOFF.md` | **完整交接规格（必读）** |
| `app.py` | CLI：`learn` `tender` `judge` `audit-judge` `sync` |
| `src/sync/api.py` | 手机同步 FastAPI 服务 |
| `mobile/index.html` | 手机 Web（PWA）校正界面 |
| `src/export/cost_analysis_template.py` | **智能成本分析模板（主路径）**：自动识别甲方列并追加统一成本区 |
| `src/export/inline_cost_link.py` | 交付入口：模板 append / 海德清单询 haide_inline |
| `src/export/inplace_bidder.py` | 老项目 18 列 inplace（校准回归保留） |
| `src/pricing/component_judge.py` | 人材机多源判断 |
| `src/pricing/sanity_check.py` | **价格数量级防线**：越界打标降级 auto_fill + 全库审计 |
| `src/pricing/fee_rates.py` | **取费库**：管理费/利润/风险 + 措施/规费/税金汇总 |
| `src/export/boq_validation.py` | **清单五要素体检**（防废标） |
| `src/knowledge/quota_manager.py` | 定额（量价分离：消耗量定额 + 外部价库） |
| `config/labor_rates.json` | 人工/机械单价（城市×工种，2026 市场口径） |
| `config/fee_rates.json` | 取费标准（按工程类别×档位） |
| `config/market_reference_prices.json` | 无历史时的市场参考价 |
| `config/settings.json` | 匹配阈值、auto_fill 0.8 |
| `清单数据资料/AI学习清单/` | 历史样本 |
| `清单数据资料/甲方招标清单/` | 招标样例 |
| `config/project_pairs.json` | 招标↔金标准↔导出 配对 |

## 常用命令

```bash
pip install -r requirements.txt
python app.py init && python app.py import-catalog
python app.py import-project-materials "清单数据资料/AI学习清单/售楼处主材料.xlsx" --project "珠海海德公馆售楼处会所" --city 珠海
python app.py relearn-all --reset
python app.py tender "招标.xlsx" --city 深圳 --tier mid --price --export
python app.py deliver --project haide_sales          # 标准交付（推荐）
python app.py calibrate --project haide_sales --learn # 对比金标准并 learn
python app.py regression                             # 全项目校准+audit 回归（改 judge 后建议跑）
python app.py deliver --project haide_club_merge       # 清单询 P列成本区+lj链接
python app.py link-inline --project haide_club_merge  # 同上（显式命令）
python app.py external-price "墙面乳胶漆" --feature "..." --city 珠海
python app.py audit-judge
python app.py extract-market-ref [--top N] [--city 深圳]   # 从知识库提炼市场参考价候选（覆盖审计）

# 造价专业校验（新增）
python app.py import-quota                   # 定额导入（config/quota_standards.json → quota_standards）
python app.py quota-cost 020201001 --city 深圳  # 定额成本（人工/机械按 城市×工种 分档）
python app.py audit-price                    # 价格数量级审计（市场参考价/定额价/人工机械单价）
python app.py quote-fees --cost 100 --quantity 1000 --category 装饰装修 --tier mid  # 取费建议（管利规税）
python app.py validate-boq "招标.xlsx"       # 清单五要素体检（编码/名称/特征/单位/工程量）

# 手机同步（电脑与手机同一 WiFi）
python app.py sync serve              # 启动 http://本机IP:8765/
python app.py sync token              # 生成远程 API Token（外网必填）
python app.py sync token --show       # 查看 Token
python app.py sync bundle             # 生成 data/sync/latest_bundle.json
python app.py sync pull               # 导出手机 pending 校正 → data/sync/mobile_corrections_*.json
python app.py sync status

# 外网远程 deliver：电脑+手机装 Tailscale → sync token → sync serve → 手机打开 100.x.x.x:8765「远程」页
# 开机自启与 Tailscale 逐步说明：docs/远程同步与开机自启.md

# 同步到 GitHub（Cursor 手机读仓库）
python app.py git-sync -m "说明本次改了什么"
```

## 下一步（摘要）

见 `docs/PROJECT_HANDOFF.md` §9：补深圳信息价、多 learn 历史项目、广联达定额 OCR、audit 监控准确率。

## 修改匹配/组价时

同步更新：`config/settings.json`、`src/match/engine.py`、`src/pricing/component_judge.py`、相关 `docs/`。

## 成本分析智能模板（主铁律，勿每次手改列号）

**甲方表格式各异，成本分析格式永远相同；** 连接逻辑只在 `src/export/cost_analysis_template.py`，按闭环金标准自动识别画像桥接。

**固定成本区（7 列，顺序不可变）**  
成本单价、主材、损耗率、人工、辅材、机械、合价  
`成本单价=主材+主材×损耗+人工+辅材+机械`；**成本合价=成本单价×工程量**

| 连接画像 | 闭环样例 | 甲方左区特点 | 桥接方式 |
|----------|----------|--------------|----------|
| `haide_inquiry` | 售楼处 / 地库 / 会所合并 | 人工、主材、辅材及机械费、综合单价、合价 | 左区只写公式：人工=成本人工×费率；主材=主材(1+损耗)×费率；辅材及机械=(辅材+机械)×费率；费率在成本主材/人工/辅材列第 1 行 |
| `tender_breakdown` | 开市客 | 综合单价 + 其中(人工费/材料费/其他费) + 合价 | 末列后空 1 列追加成本区；人工费/材料费/其他费桥接成本区；综合单价=三者之和；合价=工程量×综合单价 |
| `national_quote` | B2 户型 | 综合单价 + 合价（无其中分解） | 末列后空 1 列追加成本区；综合单价=成本单价×$费率$1；合价=工程量×综合单价 |

铁律1：甲方原有表头/样式/结构**一律不改成死数**；只追加成本区，并用公式按画像连接甲方报价列。

铁律2（母行链接绝对引用）：所有"母行链接/跨表链接/费率引用"的公式**一律全绝对引用**（`$列$行`），与 `lj` 工具一致（如 `=$U$7`、`='地上装修工程'!$Q$1`、`='[母表.xls]Sheet1'!$F$128`）。仅**同行自引用**（如 `=P7*(1+Q7)`、`=人工+辅材`）用相对。实现：`src/link/dedupe.py::master_cell_formula`（母行链接统一入口），费率引用恒为 `$列$1`。禁止在母行链接中使用无 `$` 的相对引用——筛选、排序、移动母行后引用会漂移。

闭环项目在 `project_pairs.json` 均设 `"delivery": "auto"`（自动识别画像）。  
单文件：`python app.py deliver "招标.xls"` 默认走智能模板。

| 闭环项目 | 金标准 | 校准（≤10%） |
|----------|--------|----------------|
| haide_sales | `清单数据资料/AI学习清单/珠海海德公馆售楼处会所-20260627.xlsx` | 100% |
| haide_basement | `清单数据资料/AI学习清单/珠海丹田海德地库清单-20260627.xlsx` | 100% |
| haide_club_merge | `清单数据资料/AI学习清单/珠海丹田海德公馆会所精装修工程-合并-20260705.xlsx` | 100% |
| costco | `清单数据资料/AI学习清单/02 附件二：星河开市客…20260628.xlsx` | 100% |
| b2_house | `清单数据资料/AI学习清单/B2户型装修工程清单-20260706.xlsx` | 100% |
| jiangmen_05house | `清单数据资料/AI学习清单/江门新会骏凯豪庭…-投标报价-20260818.xlsx` | 100% |
| shenhai_dasha | `清单数据资料/AI学习清单/成本分析表-深海大厦项目-20260512.xls`（多文件） | ≥95% |
| rcl_spa | `清单数据资料/AI学习清单/深圳星河丽思卡尔顿酒店5楼SPA区域装修维修改造工程报价清单20260828.xlsx` | 32/32、合价偏差 0% |
| yunwan_deco | `清单数据资料/AI学习清单/云湾花园项目-会所售楼部装修工程专业分包-投标清单-20260828.xls` | 231/231、合价偏差 0% |
| yunwan_inst | `清单数据资料/AI学习清单/02 会所售楼部安装工程清单-20260828.xlsx`（电气/给排水/空调） | 114/114、合价偏差 0% |

> rcl_spa（酒店SPA改造，深圳/高档）：报价口径=国产泳池设备工程价（口件/水下灯/马赛克 50~285）+进口设备单列（TYLO湿蒸门 2万/当代花洒 8500）+拆除恢复整项+人工上浮+综合费率 21%（F=成本×1.21，R1 费率 0.15/1.06）。注意：该类清单**表头自带成本区**（成本价/主材费/主材损耗率/人工费/辅材费/机械费/成本合计），智能模板已支持复用已有成本区列（`_cost_side`），不会重复追加；表头 name 字段需含"项目内容"别名（detector 已支持）。

> 数据净化（20260828）：`src/knowledge/facts.py::upsert_material_fact_from_line` 只从**名称**判定材料品类（特征里的"地面石材、砖"等描述词会把水泥/胶泥/防锈漆带偏成 stone/tile），规格可取名称+特征；胶水/剂类辅料走精确词表 `_AUX_MATERIAL_WORDS`（玻璃胶/云石胶/美缝剂/防护剂等）不进主材价库；整项单位（项/系统/宗）不进。全库材料价已按此净化（127→101 条，中山 39→20 条）。市场参考价按 `extract-market-ref` 候选补齐安装类：门禁系统安装(项)/喷淋管网试压与排水费(项)/金属软管(m)/ZR-RVS电线(m)。

> 云湾（会所售楼部，中山/中档）：定稿=20260828 投标清单，成本=报价口径（费率管理费0利润0主材1人工1辅材1机械1）。装修与安装表头成本区首列为**"单价合计"**（非"成本单价"），detector `_detect_appended_cost_block` 已支持识别并复用；定稿相对 20260825 旧版整体上调收口（装修按工程量净 +126 万：屏风/透光亚克力/电动移门/石材上调，墙面干挂瓷砖下调；安装 LED 灯具主材上调 50~300%、风管机按厂家工程价下调约 40%、多联机上调）。注意：定稿卫浴洁具名称带"品牌：科勒/TOTO"后缀，与旧版无品牌名称匹配键不同 → 校准计入"独有项"但金额已匹配（AI 知识库已学到品牌价）。

全部 `"delivery": "auto"`。多文件项目（深海）会对每个 tender/export 各跑一遍智能模板。

入口：`python app.py deliver --project …` → `inline_cost_link` + `cost_analysis_template`。  
定稿固化：`python app.py calibrate --project … --learn`。
