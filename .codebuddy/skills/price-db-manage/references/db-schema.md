# 组价数据库结构（data/cost_pricing.db）

> 实际 schema 以 sqlite_master 为准（`python -c "import sqlite3;..."` 可查）。本文件是字段语义与常用查询速查。

## 核心表

### projects（35 项目）
id / name / project_type(historical) / source_file / region / city / price_tier(mid) / remark
- is_verified=1 判定：source_file 在 config/project_pairs.json 登记为 gold。

### boq_lines（12660 行清单明细）
project_id / sheet_name / name / feature / unit / quantity / unit_price / amount / remark / name_norm / feature_norm / unit_norm / row_index

### standard_items（5334 标准项，唯一键 name_norm+unit_norm+method_signature）
清单项归一化后的聚合键；method_signature 区分同名多做法。

### cost_records（11130 人材机成本记录）
standard_item_id / source_project_id / material_main / material_loss_rate / material_aux / labor / machinery / management / profit / tax
**= 主材/辅材/机械/人工最细粒度来源**。

### line_price_facts（5813 清单项价事实）
standard_item_id / city / price_tier / 五列人材机 / cost_unit_price / sample_count
聚合中位；**定稿优先**（同键有 is_verified 样本只用定稿）。

### material_price_facts（550 材料价事实）
material_key(英文类名如 sand/steel) / material_category / spec_text / unit_norm / city / price_tier / material_main / sample_count
唯一键 material_key+unit_norm+city+price_tier。**材料名判定只看"名称"列**，规格可取名称+特征。

### craft_cost_profiles（433 工艺价型）
craft_type / trade / tag_key / tag_value / unit_norm / city / 五列人材机 —— 按工艺×标签聚合。

### craft_processes（12+ 工艺工序链，定稿吸收/组价时补录增长）
item_key(UNIQUE) / trade / unit_hint / process_chain(JSON: [{step, materials[], note}]) / missing_alerts(JSON) / price_anchor / source
- 由 craft-pricing 技能的 `scripts/craft_db.py init` 建表灌种子；组价第 4 步先查本表再查定额 work_content。

### quota_standards（3212 定额子目，三册）
quota_code(全局UNIQUE,02装饰/03给排水) / name / unit / labor_consumption / material_json / machinery_json / craft_category / work_content / chapter
- 装饰 SJG75：990 子目；给排水 SJG74-8：1008；电气 SJG74-2：1214
- **量价分离**：消耗量×期刊价=定额口径成本

## 配套 JSON（config/）

| 文件 | 内容 |
|---|---|
| labor_rates.json | 人工/机械 城市×工种 |
| market_reference_prices.json | 市场参考规则（2383 条，name_keywords 只匹配名称！DN 等特征词必须 feature_keywords+require） |
| fee_rates.json | 管理费/利润/风险 + 措施/规费/税金（by_style.metro_fitout=7%/6%/1%） |
| quote_styles.json | 交付 markup 系数 |
| project_pairs.json | 招标↔金标准↔导出配对（gold 登记才产生定稿样本） |

## 常用查询

```sql
-- 某清单项历史价（深圳/中档）
SELECT * FROM line_price_facts f JOIN standard_items s ON s.id=f.standard_item_id
WHERE s.name_norm LIKE '%块料楼地面%' AND f.city='深圳';

-- 某材料价
SELECT * FROM material_price_facts WHERE material_key LIKE '%cable%';

-- 定额子目
SELECT quota_code,name,unit FROM quota_standards WHERE name LIKE '%块料楼地面%';
```

## 已知口径注意

- fees.材料费 967 子目解析坏（927 个<10，列对齐问题）——材料费总额锚不可用，定额层校验用人工费锚。
- OCR 消耗量已三层修复（行级中位锚/品类物理区间/基期价区间），残留超 15 倍口径行 188（5.8%）靠下游偏离守卫。
- 期刊价=市场零售口径，系统性高于合同批量口径 30~100%——这是市场参考层精度天花板，line_match（有历史样本时 0.90）依然最准。
