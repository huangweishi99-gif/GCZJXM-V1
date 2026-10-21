---
name: craft-pricing
description: 对清单项做成本组价分析——按"识别分项→解析特征→锁定单位→拆解工艺流程→逐工序算人材机→价格来源分级→汇总"的固定八步法执行，对比项目特征描述找出缺漏/多余的工序，输出工序拆解表和待确认清单。当用户要求"组价/成本分析/拆工艺/这项多少钱/核这个价"时使用。禁止直接套相似历史单价了事，禁止 LLM 拍价入库。
---

# 工艺拆分组价标准（八步法）

## 铁律

1. **不允许直接套一个"相似历史单价"了事**——必须拆到工序层。
2. **LLM/AI 拍价禁止入库；无价源宁留空**（留空并在备注标"待询价/待确认"）。
3. 每个单价必须标注**价格来源**和日期；网查价标"参考价，待核实"。
4. 描述里没写的参数列为"待确认"，**不自行假设**。

## 八步流程

1. **识别分项**：项目名称判断分项工程（块料楼地面/墙面喷刷涂料/电力电缆…）。
2. **解析特征**：从项目特征逐条提取材料品种、规格型号、厚度/强度等级、做法、部位；缺参数记"待确认"。
3. **锁定计量单位**：以清单计量单位为基准（m²/m/m³/个/项/t），所有消耗量换算到"每 1 个计量单位"。
4. **拆解工艺流程**：按实际施工顺序列每道工序；**先查工艺数据库** `scripts/craft_db.py query <分项名>`（`craft_processes` 表 = 正式工艺工序链 + `seed-quota` 生成的定额材料构成候选，`[定额候选]` 标识仅作材料提示，工序顺序仍按特征拆）；定额 `work_content` 导入时未填充（实测全 NULL），定额侧参考用 `app.py quota-cost <编码> --city <城市>` 试算人材机；最后对照项目特征：**特征写了的工序必须组到价里；特征没写但工艺必需的工序，列入"待确认缺漏"**。新确认工艺用 `craft_db.py add` 补录。
5. **逐道工序算人材机**：人工=工日×人工单价；材料=消耗量×(1+损耗)×单价；机械=台班×台班单价。
6. **价格来源优先级（高→低）**：
   ① 用户历史投产成本库（cost_records/定稿样本，定稿优先）
   ② 深圳信息价期刊 CSV（2026年9月信息价，material_price_mapper）
   ③ 定额口径（quota_standards 消耗量×城市工日价——量价分离）
   ④ 同类项目历史数据（line_price_facts 中位）
   ⑤ 市场参考价 config/market_reference_prices.json
   ⑥ 网上查询（必须标"参考价，待核实"+网站+日期，**不入库**）
7. **汇总**：各工序小计相加 → +管理费、利润（费率按 fee_rates.json/quote_styles.json 项目口径）→ 综合单价。损耗率列填小数（0.02）。
8. **输出**：先工序拆解表（模板见 `references/pricing-procedure.md`），再综合单价；最后必须附**"待确认参数"和"缺数据单价"清单**。

## 与现有系统的对接

- 批量组价走 `app.py tender/deliver`（judge 引擎 + sanity_check 数量级防线）；单条精组价按本八步法人工拆，结果可回填成本区五列。
- 组价引擎已覆盖常见价型（component_judge 优先权：power_cable > lighting > project_material > metal_trim > is_special_item > line_match > custom_door > custom_furniture > line_match_weak > paint > market_reference）；引擎结果**仍需按工序拆解复核**，特别是备注标"复合做法需工序拆分复核"的行。
- 拆除工程按"拆除+清运"两工序起步，数据见 price-db-manage 技能的拆除分类。

## 参考与脚本

- `references/pricing-procedure.md` — 八步法详细规程 + 输出表格模板（来自 03b-codebuddy-pricing-prompt.md）。
- `references/craft-process-library.md` — 常用分项标准工序链（块料楼地面/乳胶漆/真石漆/防水/吊顶/石材/拆除/电缆敷设…），与工艺数据库同源，新确认工艺两处同步补录。
- `scripts/craft_db.py` — 工艺数据库管理：`init`（建表+灌种子）/ `query`（组价第 4 步先查它）/ `add`（补录新工艺）。
