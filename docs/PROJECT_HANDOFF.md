# 项目交接规格（PROJECT HANDOFF）

> **Codex / 新 Agent / 开发者：先读 [`CODEX.md`](../CODEX.md)（一键接手），再读本文全文。**  
> **国内 TRAE IDE：先读 [`TRAE_HANDOFF.md`](../TRAE_HANDOFF.md)，再读本文全文。**  
> 编码速查：[`AGENTS.md`](../AGENTS.md)  
> 更新日期：**2026-08-18** · 仓库：https://github.com/huangweishi99-gif/GCZJXM-V1

---

## 0. Codex 一键接手清单

```powershell
# 1. 环境
pip install -r requirements.txt && python app.py init && python app.py import-catalog

# 2. 知识库（克隆仓库后必做；本地已有 data/cost_pricing.db 可跳过 --reset）
python app.py relearn-all --reset

# 3. 验收（改 judge/匹配/导出 前后都要跑）
python app.py regression
python app.py audit-judge --limit 500
python app.py audit-review --top 80

# 4. 标准交付试跑
python app.py deliver --project haide_sales
python app.py deliver --project b2_house
```

| 验收项 | 通过标准 |
|--------|----------|
| `regression` | `"ok": true`，七套闭环 `within_10pct` 100% |
| `audit-judge` | `core_main_and_labor` ≥ 45%（目标 80%）；见 `data/exports/audit_judge_summary.json` |
| `audit-review` | 生成 `data/exports/待确认清单_人材机判断.xlsx`，优先处理高风险前 20 行 |
| 交付铁律 | 甲方原表未被改结构；成本区 7 列顺序固定；合价 = 成本单价 × 工程量 |

---

## 1. 项目目的

**本地化智能清单组价系统**：从历史项目 Excel（清单 + 人材机成本拆解）建 SQLite 知识库，对甲方招标清单按「名称 + 项目特征 + 单位 + 城市档位」匹配填价，**在原招标 Excel 上追加成本分析列**导出，同表去重母行 + 公式链接。

**用户价值**：不同甲方表格式各异，但输出成本分析格式统一；减少手工组价与重复填价。

**不在范围内（当前）**：广联达定额 PDF 自动 OCR 套算（扫描件未入库）、云端默认上传造价资料。

---

## 2. 业务铁律

### 2.1 清单语义

| 字段 | 含义 |
|------|------|
| **项目名称** | 做什么；主材/面层品类多在名称里 |
| **项目特征** | 施工步骤（≈ 定额「工作内容」）；逐条比对 |
| **组价** | 名称 **且** 特征 **且** 单位都接近 → 整项套历史；否则专项价型 / 市场参考 / 不填 |

### 2.2 定额与物料口径（用户确认）

- **无机涂料 = 乳胶漆** → 匹配、套价同乳胶漆（`src/normalize/paint_equiv.py`）。
- **ST / CT / WD / PT / MT 等编号** = **该项目**物料书代号，**不跨项目**当同一物料单价。
- **清单单位 ≠ 定额单位** → 先换算再汇总（如门槛石常用 **m**，勿按 ㎡ 中位数套）。
- **公区 vs 户内**：B2 户内专项规则不得套用到会所/地库/公区（`residential_finish_price.py` 门禁）。

### 2.3 成本分析交付铁律（最高优先级）

**甲方表格式各异，成本分析格式永远相同。**

- 甲方原有表头、数据、样式、合并单元格 **一律不改**。
- 在甲方 **最后一列后空 1 列**，追加固定 **7 列**（顺序不可变）：

  `成本单价 | 主材 | 损耗率 | 人工 | 辅材 | 机械 | 合价`

- 公式：`成本单价 = 主材 + 主材×损耗率 + 人工 + 辅材 + 机械`；**合价 = 成本单价 × 工程量**。
- 连接逻辑 **只** 在 `src/export/cost_analysis_template.py`（`detect_connection_profile` + 画像桥接），**禁止**在每个项目里写死列号。

| 连接画像 | 闭环样例 | 甲方左区 | 桥接 |
|----------|----------|----------|------|
| `haide_inquiry` | 海德售楼处/地库/会所 | 人工、主材、辅材及机械、综合单价、合价 | 左区写公式引用成本区 + 第 1 行费率 |
| `tender_breakdown` | 开市客 | 综合单价 + 其中(人工/材料/其他) + 合价 | 末列后追加成本区，桥接其中三费 |
| `national_quote` | B2 户型 | 综合单价 + 合价 | 综合单价 = 成本单价×费率；合价 = 量×综合单价 |

入口：`python app.py deliver --project <id>` → `inline_cost_link.py` → `cost_analysis_template.py`。

---

## 3. 系统架构

```text
清单数据资料/
  AI学习清单/          ← learn 入库 + 解剖报告
  甲方招标清单/        ← tender / deliver 输入

app.py                 ← CLI 总入口
src/ingest/            ← detector（表头）parser（解析+公式求值）
src/match/             ← 名称/特征/标签匹配 engine
src/knowledge/         ← learn、calibration、repository、anatomy、quota_manager（定额量价分离）
src/pricing/           ← component_judge（核心）、market_reference、各专项价型
  sanity_check.py             ← 价格数量级防线（越界打标降级 auto_fill + 全库审计）
  fee_rates.py                ← 取费库（管利险 + 措施/规费/税金汇总）
src/export/
  cost_analysis_template.py   ← 智能模板（主交付）
  inline_cost_link.py         ← 填价+去重链接入口
  inplace_bidder.py           ← 老 18 列路径（回归保留）
  boq_validation.py           ← 清单五要素体检（防废标）
config/
  project_pairs.json          ← 六套闭环 招标↔金标准↔导出
  settings.json               ← 匹配阈值、auto_fill 0.8
  market_reference_prices.json
  craft_trade_rules.json
  labor_rates.json            ← 人工/机械单价（城市×工种，2026 市场口径）
  fee_rates.json              ← 取费标准（工程类别×档位）
  quota_standards.json        ← 定额消耗量（→ quota_standards 表）
data/cost_pricing.db            ← SQLite（本地重建，不进 Git）
data/exports/                 ← 导出、regression/audit 摘要
mobile/ + src/sync/           ← 手机校正 PWA + FastAPI
```

---

## 4. 完成度矩阵（2026-07-07）

### 4.1 已稳定（可依赖）

| 模块 | 状态 | 说明 |
|------|------|------|
| 智能成本分析模板 | ✅ 生产 | 三画像自动识别；六项目 `delivery: auto` |
| 闭环校准 | ✅ 100% | 六套金标准 ±10% 全过（`python app.py regression`） |
| learn + 解剖 | ✅ | 每次 learn 出 `data/exports/解剖报告/` |
| 公式求值读金标准 | ✅ | `formula_eval` + parser/inline 读成本 |
| 跨表去重链接 | ✅ | MasterRowRef + 公式引用母行 |
| 项目主材编号价 | ✅ | PT/ST/CT + 工序分解 |
| 弱匹配拦截 | ✅ | 主材编号冲突、特征产品名冲突、泛称提高门槛 |
| 分城市场价 | ✅ | `sz_` / `zh_` 优先；通用规则默认不 auto_fill |
| 价格数量级防线 | ✅ | `sanity_check`：越界打标降级 auto_fill；`audit-price` 全库 0 越界 |
| 定额量价分离 | ✅ | `quota_manager`：消耗量定额 + 城市×工种人工/机械价 + 外部价覆盖 |
| 取费库 | ✅ | `fee_rates`：管理费/利润/风险 + 措施/规费/税金汇总（merge 顺序 default→tier→category） |
| 清单五要素体检 | ✅ | `boq_validation`：编码/名称/特征/单位/工程量；补充清单项（含字母编码）提示不误报 |
| 手机 sync | ✅ | `python app.py sync serve` |

### 4.2 七套闭环项目

| project_id | 标签 | 金标准 | 校准 |
|------------|------|--------|------|
| `haide_sales` | 珠海海德公馆售楼处 | `AI学习清单/珠海海德公馆售楼处会所-20260627.xlsx` | 166/166 |
| `haide_basement` | 珠海海德地库 | `AI学习清单/珠海丹田海德地库清单-20260627.xlsx` | 78/78 |
| `haide_club_merge` | 会所合并清单询 | `AI学习清单/珠海丹田海德公馆会所精装修工程-合并-20260705.xlsx` | 304/304 |
| `b2_house` | B2 户型 | `AI学习清单/B2户型装修工程清单-20260706.xlsx` | 55/55 |
| `costco` | 星河开市客 2 楼公区 | `AI学习清单/02 附件二：…20260628.xlsx` | 75/75 |
| `jiangmen_05house` | 江门批量精装 05 户型 | `AI学习清单/江门新会骏凯豪庭…-投标报价-20260818.xlsx` | 84/84 |
| `shenhai_dasha` | 深海大厦北塔（多文件） | `AI学习清单/成本分析表-深海大厦项目-20260512.xls` | 160/160 |

配置：`config/project_pairs.json`。

### 4.3 进行中（质量未达标）

| 模块 | 当前 | 目标 | 主要问题 |
|------|------|------|----------|
| `audit-judge` 全量核心准确 | **71.8%** | 80% | `generic_finish`/通用市场价仍需继续拆专项 |
| `audit-review` 待确认清单 | 已可用 | 复核闭环 | 从 audit 明细按风险标签导出人工优先级 |
| 自动填入子集核心准确 | **100%**（auto_fill 9.2%） | 80% 后逐步扩覆盖 | 已收紧低可信 auto_fill；编号/机电弱整项、市场份额拆分、风口/灯具代号等先降级复核 |
| `market_reference` | 53.5% 核心 | ↑ | 已补一批明确名称的复核参考价；项目编号/包干项仍需谨慎 |
| `mep_install_profile` | 78.7% 核心 | ↑ | 电缆截面、桥架宽度、JDG/消防配管、配线多芯、消防弱电/通风/电表/阀门/末端试水装置/移位配电箱附件已收敛一版；冷媒、CL 涂料仍需继续 |
| `unresolved` | 3/500 | ↓ | 剩余为项目编号/包干大项；块料踢脚、镜子安装、SP 手绘壁画已给复核参考价 |
| 广联达定额 OCR | 部分落地 | quota_items | 已导入 73 条 JSON（`config/quota_standards.json` → `quota_standards` 表）；PDF 扫描件全量 OCR 未做 |

**最新指标文件**：`data/exports/audit_judge_summary.json`、`data/exports/regression_summary.json`。

---

## 5. 填价优先级（`component_judge.py`）

实际链路（简化；以源码为准）：

```text
special_line / residential / decorative_diffuser / lighting_fixture …
        ↓
mep_install（VRF、洁具、冷媒、断路器等；电缆估算法仅参考）
        ↓
项目主材编号 PT/ST/CT + 工序分解
        ↓
历史整项 line_match（名称+特征+单位，exclude_self）
        ↓
弱整项（拦截编号/产品名冲突；泛称需更高 feature 分）
        ↓
金属线条 / 定制门家具 / 瓷砖工艺 / 涂料 paint_process / CL 天花涂料
        ↓
历史弱整项 fallback（1g）
        ↓
电缆配管 / 零散成品 fallback（仅 line_conf 不足时）
        ↓
市场参考 market_reference（城市定稿规则才可 auto_fill）
        ↓
工艺价型 craft_profile（非 generic_finish + sanity）
        ↓
主材价库 + 工艺份额模板（散装材料如水泥吨 → 仅主材，不套份额）
        ↓
unresolved / 备注人工组价
```

阈值：`config/settings.json` → `component_judge.auto_fill_confidence` = **0.8**。

---

## 6. 开发习惯与编码约定

### 6.1 用户 / 项目习惯

- 每次给新 Excel → **`python app.py learn`**（自动解剖），不是只改 JSON 规则。
- 定稿后 → **`calibrate --project … --learn`** 固化进知识库（见 `docs/闭环学习流程.md`）。
- 改匹配或 judge → **`regression` 必须全绿** 再交付。
- **不主动 git commit**（除非用户明确要求）。
- 回复用户用 **中文**；代码注释可中文业务说明。

### 6.2 代码约定

- 表头列位：**只用** `src/ingest/detector.py`，禁止 `ws["P1"]` 类硬编码。
- 成本区列位：**只用** `cost_analysis_template.effective_client_last_column` + 画像。
- 新价型：进 `component_judge` 对应层，或独立 `src/pricing/*.py` + 在 judge 中挂接。
- 市场价：优先 `sz_` / `zh_` 前缀；`note` 含「定稿/海德」的可 auto_fill；通用规则仅参考。
- 最小 diff：不重构无关模块；匹配现有命名与 import 风格。
- 无机涂料项走乳胶漆等价，勿单独造「无机」匹配分支（除非工序特殊如 CL 灯槽）。

### 6.3 修改检查清单

- [ ] 表头/detector，不写死列号
- [ ] 改 `settings.json` / `match/engine.py` / `component_judge.py` 时同步相关 `docs/`
- [ ] 新填价走 `component_judge`，不绕过 `line_identity` 特征校验
- [ ] 跑 `python app.py regression`
- [ ] 交付样本 eyeball：甲方区无被动过

---

## 7. 常用命令

```powershell
# 环境
pip install -r requirements.txt
python app.py init && python app.py import-catalog
python app.py relearn-all [--reset]

# 学习 / 交付 / 闭环
python app.py learn "清单数据资料/AI学习清单/某项目.xlsx" --city 珠海 --tier mid
python app.py deliver --project haide_club_merge
python app.py deliver "清单数据资料/甲方招标清单/招标.xls" --city 珠海
python app.py calibrate --project haide_sales --learn

# 诊断
python app.py judge "项目名称" --feature "特征" --unit ㎡ --city 深圳 --tier mid
python app.py audit-judge [--limit 500]
python app.py audit-review [--top 80]
python app.py regression
python app.py stats

# 造价专业校验
python app.py import-quota                              # 定额导入（quota_standards.json → 表）
python app.py quota-cost 020201001 --city 深圳          # 定额成本（人工/机械按 城市×工种）
python app.py audit-price                               # 价格数量级审计（市场/定额/人工机械单价）
python app.py quote-fees --cost 100 --quantity 1000 --category 装饰装修 --tier mid   # 取费建议
python app.py validate-boq "招标.xlsx"                  # 清单五要素体检

# 手机同步
python app.py sync serve
python app.py sync token --show
```

---

## 8. 知识库规模（参考）

本地 `data/cost_pricing.db`（2026-07 典型值）：

- cost_records ~6300+
- boq_lines ~49000+
- standard_items ~4100+

克隆仓库后执行 `relearn-all --reset` 从 `清单数据资料/AI学习清单/` 重建。

**待 learn 样本**（提高强匹配）：理想汽车框架清单、竹村幕墙、商超店框架、中山医院等（见该目录下 xlsx/xls）。

---

## 9. 当前进行到哪一步

```text
[已完成] 交付链路 + 六套闭环校准 100%
[已完成] 智能模板三画像 + 公式桥接 + 跨表链接
[已完成] 弱匹配收紧 + 分城市场价 + MEP/涂料/断路器专项（第一版）
[已完成] audit-review 待确认清单 + judge 解释摘要/风险标签
[已完成] 价格数量级防线 + 全库 audit-price 0 越界
[已完成] 定额量价分离（quota_standards 73 条）+ 城市×工种人工/机械价
[已完成] 取费库 + 清单五要素体检命令
[进行中] audit-judge 全量核心准确 72.8% → 目标 80%
[进行中] 压低 unresolved/generic_finish → 拆门窗、纯材料代号、项目包干专项
[进行中] learn 未入库历史项目 → 提高 line_match 占比
[未开始] 广联达装饰册全量 OCR → quota_items
[未开始] audit-judge 纳入 CI / learn 后自动跑
```

### 建议下一步（按 ROI）

| 优先级 | 任务 | 主要改动位置 |
|--------|------|--------------|
| **P0** | learn 未入库历史清单 | `python app.py learn …` |
| **P0** | 处理 `audit-review` 高风险前 20 行 | `data/exports/待确认清单_人材机判断.xlsx` → 对应专项规则/市场价 |
| **P1** | 从六套金标准提炼 `zh_`/`sz_` 市场价（✅ 2026-08-25 已工具化：`extract-market-ref` 自动聚合候选 + 覆盖审计；60 簇 53 已覆盖、7 未覆盖均已被其他来源正确处理，规则库已完备） | `config/market_reference_prices.json` + `src/pricing/extract_market_ref.py` |
| **P1** | 压低 `generic_finish` / 剩余 `unresolved` | `craft_trade_rules.json` + `special_line_price.py` / `custom_door.py` |
| **P1** | 电缆/桥架/JDG/消防配管/配线/消防弱电/通风/电表/阀门附件已修一版；继续补冷媒、CL 无机涂料灯槽/边槽 | `mep_install_price.py` / `material_process_price.py` |
| **P2** | regression 后自动 audit + 阈值门禁 | `app.py` relearn-all --audit |
| **P2** | 定额 OCR 全量 | 已有 `quota_standards` 73 条；补 PDF 扫描件 OCR → `quota_items` 全量 |

---

## 10. 已知坑与教训

| 问题 | 对策 |
|------|------|
| 工艺价型中位数「高置信低准确」 | 已降权；`generic_finish` 禁止 craft_profile sanity 通过 |
| 弱整项同名异规 | `_weak_candidate_rejected` 拦截编号/产品名 |
| 低置信弱整项被自动采纳 | `line_match` 低于 0.8 且含项目编号/机电规格时降级为人工复核 |
| 市场参考合价拆分偏分项 | `market_reference` 含项目编号、喷白或按工艺份额拆分时降级为人工复核 |
| 通用市场参考分项过粗 | 对窗帘盒、防雨空调室外机配电箱、水压试验/系统调试、暗藏检修口、双头射灯、墙板/SF、涂料、防火涂料、环氧自流平、保温卷帘门等明确名称项补复核参考价；规则不使用 `sz_`/`zh_` 前缀，避免自动填入扩张 |
| 涂料顶棚编号误命中 | `涂料顶棚D1` 规则必须用完整名称 + 工序特征，不得用裸 `D1`，避免误套 `D16` 等编号 |
| 拆除兜底过粗 | 金属构件拆除、钢筋混凝土构件拆除、风机盘管保护性拆除补窄口径复核参考价；拆除+新做复合项仍保留人工复核 |
| 专项价型覆盖但分项波动大 | 风口规格换算、照明代号、冷媒/软接、灯槽延米等保留参考价但不自动填 |
| 金属线条被弱整项抢价 | 明确“展开面 xx mm”的不锈钢/古铜/MT 收口条优先走 `metal_trim_profile`；基层描述不再阻断 |
| 明确小项被弱整项覆盖 | 石膏板（张）、CFC 保温、外围木板基层、内嵌卡座、设备三相四孔插座、双扇玻璃门、玻璃钢隔油池、SBS 平面防水卷材、成品软膜灯箱等小项优先走 `special_line_price` 复核参考 |
| 金标准单元格是公式 | `data_only=False` + `formula_eval` |
| 综合单价当成本 | parser 优先分量成本，再扣管理费 |
| 保温厚度误当冷媒管径 | 冷媒管解析用 Φ 而非「20mm 保温」 |
| 断路器被照明代号吃掉 | `lighting_fixture_price` 排除 NXBLE/NM1 |
| 电缆截面公式抢历史强匹配 | 电缆专项在 line_conf 不足时用；估算法暂不 auto_fill |
| 电缆规格在名称/特征重复出现 | 名称中有明确线缆型号时优先采用名称规格；否则再读特征中的单个 `规格:`，避免通用 `2.5` 覆盖名称型号或重复累加截面 |
| 中文清单 `DN150新增` 管径解析 | 管径正则用“后接非数字”而非 `\b`，避免抓成其他序号 |
| 线槽/桥架人工偏低 | 桥架人工按宽度 `18 + 宽度×0.10`，JDG15/20/25/150 用规格小表兜底 |
| 多芯配线被当单芯 | `RVV-7*1.5`、`RYS-B2-2X2.5` 等按芯数×截面总量估算，避免只取末尾截面 |
| 市场参考分项被工艺模板二次拆分 | 已有可信分项拆分的市场参考规则可设 `preserve_components`，如挂耐水腻子保留 7.6/7.2/3.8/0.38，避免抹灰找平模板把主材压到极低 |
| CL 灯槽/边槽拆分偏离定稿 | `ceiling_cl_paint` 按深海定稿分项拆解：灯槽 86.12/55.72/106.37/5.07，边槽 129/83.47/159.35/7.59 |
| 饰面修补/窄板被 material_plus_template 误拆 | 过门石、局部瓷砖修补、石材窄窗台板、面包砖、防辐射细石混凝土、瓷砖排水明沟进 `special_line_price` 精确参考；ST/CT 等项目编号仍不跨项目泛化 |
| B2 户型精装定稿编号偏差 | `residential_finish_price` 对 AB1287 坐便器、N2 防水墙砖、D3 吊顶、淋浴间玻璃隔断设定稿分支；公区门禁仍保留 |
| LED 线性灯代号价偏低 | `Rm/Lc/Ls` 灯带、硬灯条统一按 35/5/18；`T.2 LED硬灯条` 单独按 22/0.5/8 |
| 零散机电附件 unresolved | 金属软管 DN20/25、24/48 口配线架、水表 DN40、末端试水装置 DN25、闸阀/截止阀 DN20、止回阀 DN65/DN100、消防弱电模块、通风器、智能电表、七氟丙烷 70L、移位配电箱进 `mep_install_price` 兜底，均按复核参考价处理 |
| 零散成品/措施项 unresolved | 镜子、块料踢脚、SP 手绘壁画、停车位车档、货架安装、条形灯/路灯、电视硬盘道闸、柜体层板、硬木夹板门、小市政土建、纯材料小件等进 `special_line_price`，仅作参考不自动填 |
| vent_band 校准键 | deliver 时不用 vent_band 聚合价 |
| `[安装工程清单]` 特征前缀 | `normalize_feature` 只剥标签保留内容 |
| `material_main` 组件误校验 | 表示「元/㎡ 主材费」，不能当「元/kg 材料单价」或「kg/㎡ 单耗」校验 → 越界防线只做粗粒度（5~10000 元/㎡），避免乳胶漆 5.5 元/㎡ 误报 |
| `check_components` 读错键 | 曾读不存在的 `cost_unit_price` 把综合单价误报为 0 → 移除该键校验 |
| 取费 merge 顺序 | tier 曾覆盖 category → 标准应为 `default → tier → category`（类别优先，档位兜底） |
| 补充清单项编码 | 含字母编码（如 `011302B003001`）是广联达补充项格式，`validate-boq` 作提示而非警告 |
| 定额价越界误报 | 定额子目含材料价超过市场参考价上限时，仅打标不阻断（定额价 = 消耗量×外部价，允许更高） |

---

## 11. 文档索引

| 文档 | 内容 |
|------|------|
| [`CODEX.md`](../CODEX.md) | **一键接手**（5 分钟） |
| [`AGENTS.md`](../AGENTS.md) | Agent 速查 + 成本模板铁律 |
| `docs/闭环学习流程.md` | 交付→校正→calibrate→learn |
| `docs/人材机判断机制.md` | component_judge + audit |
| `docs/项目特征与施工工艺.md` | 名称/特征铁律 |
| `docs/清单定额与组价原理.md` | 清单 vs 定额、单位换算 |
| `docs/项目石材与主材编号价库.md` | ST/CT/WD 项目内编号 |
| `docs/远程同步与开机自启.md` | Tailscale + sync |
| `docs/lj链接程序解读与融合方案.md` | 海德清单询链接逻辑 |

---

## 12. Git 约定

- **提交**：源码、`config/`、`docs/`、`AGENTS.md`、`CODEX.md`、学习清单 xlsx/xls。
- **不提交**：`data/cost_pricing.db`、`data/exports/*.xlsx`、广联达大 PDF（见 `.gitignore`）。
- 克隆后：`relearn-all --reset` + `import-catalog` 恢复组价能力。

---

*重大里程碑或铁律变更时，同步更新 `CODEX.md`、`AGENTS.md`、本文件。*
