---
name: price-db-manage
description: 组价数据库的录入、查询、维护标准——主材/辅材/机械/人工/拆除五类价源的分层存储位置、新项目数据录入 SOP、组价时的调用链、录入后回归验证防污染。当用户要求"录入新价格/查某个材料多少钱/数据库管理/学入清单/为什么组价又错了"时使用。
---

# 组价数据库管理标准

## 五类价源存在哪（分层）

| 类别 | 存储 | 说明 |
|---|---|---|
| **主材** | `material_price_facts`（550 条，键=材料×单位×城市×档位）+ 期刊 CSV（深圳2026.09，1944 条）+ `market_reference_prices.json` | 规格价优先期刊，期刊没有才用历史事实中位 |
| **辅材** | 历史成本事实的辅材列（cost_records.material_aux）+ 定额材料表 | 胶水/砂浆/水泥等按 `_AUX_MATERIAL_WORDS` 词表判定，不进主材价库 |
| **机械** | `labor_rates.json` 台班价 + 定额机械行（quota_standards.machinery_json） | |
| **人工** | `config/labor_rates.json`（城市×工种：深圳 装饰232/安装212/普工153/高级技工256） | 期刊每月对齐一次 |
| **拆除** | `market_reference_prices.json` demolition_* 规则 + 历史拆除样本 | 拆除价型走 craft-pricing 技能"拆除+清运"工序 |

结构明细见 `references/db-schema.md`。查询用 `scripts/db_query.py`。

## 录入 SOP（新项目数据进来时）

1. **定稿清单（主入口）**：走姊妹技能 `finalize-absorb`——"定稿"即触发 `absorb_final.py` 一键闭环（登记 gold→备份→基线→learn→验证 is_verified→回归→报告），禁止跳过回归静默入库。不要手工拼 learn 命令。
2. **定稿优先聚合**：同键已有定稿样本时只用定稿取中位（禁止删旧版本样本去噪——实测掉准确率）。
3. **手工零星录入**（如询价回来的设备价）：`python scripts/db_query.py add-material --name 铜闸门 --spec DN300 --unit 个 --city 深圳 --price 8500 --source 厂家询价2026-10`。
4. **录入后必做回归**：定稿吸收已内置回归；零星手工录入后须手动跑 `audit-judge --limit 500` 对比基线（指标从 `data/exports/audit_judge_summary.json` 读，stdout 同指标名 40 处勿直接解析）。
5. **期刊月度更新**：新期刊丢 `pipeline/ocr_master.py` 改页码跑六脚本 → merge 进 market_reference（cities=["深圳"]）。

## 调用链（组价时系统怎么用库）

`component_judge` 优先权：power_cable > lighting > project_material > metal_trim > is_special_item(market_reference) > line_match(历史) > custom_door > custom_furniture > line_match_weak > paint > market_reference。
- 规则价改完必须同时跑基线(--limit 500)与定稿(--gold-only)两套口径 + regression（曾踩过单口径假回归/漏回归）。
- 数量级防线 `sanity_check`：越界自动打标降级 auto_fill；`audit-price` 全绿才算完。

## 防组价错（每次组价前自查）

- [ ] 主材价有源吗？（期刊>定额>定稿>市场参考>网查——网查不入库）
- [ ] 同名多做法拆了吗？（规格/厚度/品牌/遍数不同 = 不同价，不拿一条规则盖）
- [ ] 复合特征拆工序了吗？（见 craft-pricing 工艺库）
- [ ] 损耗率是小数吗？单位换算到每 1 计量单位了吗？
- [ ] 整项单位（项/系统/宗）不进单价聚合（包干价≠可比单价）。

## 红线

- LLM/AI 拍价禁止入库；无价源宁留空。
- 学入文件路径用绝对路径归一（防同文件学成多个 project）。
- 回滚点：`data/cost_pricing.db.bak_*`；批量改库前先备份。

## 参考与脚本

- `references/db-schema.md` — 全部表结构、字段含义、常用查询。
- `scripts/db_query.py` — 查材料价 / 查清单项历史价 / 手工录入材料价。
