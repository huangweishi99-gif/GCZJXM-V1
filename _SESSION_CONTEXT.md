# 会话上下文交接单 — 工程造价智能组价系统

> **使用方法**：在新对话框中输入「读取 _SESSION_CONTEXT.md」即可恢复工作状态

## 当前状态（截至本次对话）

### 核心指标
> 2026-09-04 起回归口径统一：regression 与 audit-judge 均排除模拟/框架清单样本与费项行；09-08 起 CLI 默认同口径。
| 指标 | 当前值 | 目标 | 备注 |
|------|--------|------|------|
| auto_fill_rate | **0.8043** | ≥0.85 | limit500 排除后 373 真实样本 |
| core_main_and_labor | **0.6622** | ≥0.90 | 373 样本；09-08 轮 0.6595→0.6622 |
| 校准对齐 | **10/10 套 100%** | — | amount_delta≈0，无回退 |

### 2026-09-08 完善升级轮（regression ok，failures 空）
1. **CLI 口径统一** `app.py` — `audit-judge`/`audit-review --refresh` 默认排除模拟/费项样本（旧 CLI 默认包含，曾致抽检报告误含 10671 行未过滤明细、与 regression 口径不符）；flag 反转为 `--include-simulated`/`--include-fee`，无外部脚本依赖。
2. **审计根因钻取结论**：残余失败 ~127/373 绝大多数为**同键口径冲突**（新 learn 中山/经济型样本 vs 珠海/深圳中档通用规则）——如找平砂浆在样本中主/辅归类相反（珠海辅36.8 vs 中山主8.5）、多联机 FQ 档与不锈钢线条规格级差等。**改规则会砸另一侧，不建议硬套中值**（与既有记忆一致）。
3. **低风险规则补齐** `config/market_reference_prices.json`：深圳湿蒸筒灯 155/40/6（区别于普通筒灯 70，SPA 防水灯）、地弹簧 450/副（纯五金，exclude 玻璃整门行防误伤）。分歧器 FQ01/多联式室外机为数据冲突，未动。
4. 效果：limit500 373 core 0.6595→0.6622、全量 8014 core 0.6603→0.6606，校准 10 套保持 100%。

### 2026-09-07 审计校准轮（regression ok，failures 空）
1. **管内穿线重校** `mep_install_price.py` — 废弃旧 125+1.4×截面 公式（取自 20260701 旧版清单异常行 139 元/m），按会所合并清单-20260705 定稿口径建表：2.5→主3.20/人1.50、4→4.90/2.00、6→7.30/2.20、10→12.50/2.50、16→18.20/2.80（辅0.18 机1.14）
2. **BVR 软线** `mep_install_price.py` — 2.5mm² 主 2.25→3.50、人 2.4→1.25（旧值误套 ZR-RVS 2*1.5 样本）
3. **地面插座** `mep_install_price.py` — 85/15 → 会所定稿 135/12/辅0.5/机0.5
4. **UPVC 排水管** `plastic_pipe.py` — 新增独立口径表：DN50 主10/人20、DN75 18/45、DN100 36/55（与 PPR 给水管区分，双定稿源一致）；UPVC 冷凝水管补 DN40 14/18/辅1/机0.1，匹配词加「冷凝水」
5. **嵌入式可调射灯** `lighting_fixture_price.py` — L 代号明装/嵌入式分流：嵌入式 115/辅1.5/人22/机0.3（云湾安装定稿 8 条），人工高(115)仅限明装
6. **条形风口人工占比** `decorative_diffuser.py` — total 100~200 档人材比 0.69/0.28 → 0.70/0.25（2000×150 单层百叶实样校准）
7. **纯材料小项** `special_line_price.py` — 补合页 25 元/个、晾衣杆 70 元/m（unresolved 5→2）
8. **风管机** `residential_finish_price.py` — 3600/1000/1200/45 → 3050/185/45/5.5（旧值把设备整价误入人工/辅材）

效果：core 0.7365→0.7649（+10 样本）、auto 0.7252→0.7365。剩余失败集中在 market_reference(31/125)、mep_install(9/23)、line_match_weak(8/26) —— 多为跨项目同键口径冲突（如大便器/通风机/不锈钢线条规格档），样本间主材 2.4~41.5 级差大，非规则 bug，不建议硬套中值。

### 关键改进已落地
1. **配管JDG定价校准** — `mep_install_price.py`
   - JDG15: 主材2.76, 人工11.27, 辅材1.58, 机械0.0
   - JDG20: 主材5.57, 人工12.35, 辅材0.51, 机械0.58

2. **市场参考价auto_fill修复** — `component_judge.py`
   - 修复`is_special_item`路径强制`auto_fill_ok=False`问题
   - 改为confidence≥0.75即可自动填充

3. **配电箱元器件规则** — `market_reference_prices.json`
   - 新增C20A/1P、C32A/1P带漏保、C63/3P三条规则
   - 添加exclude_name_keywords防止断路器误匹配

4. **断路器定价优化** — `mep_install_price.py`
   - 检测"配电箱元器件"特征，使用专用安装人工25元
   - 区分带漏保/不带漏保

### 下一步行动计划（Todo List）

#### 优先级：高
- [ ] **优化`_market_ref_failures.py`分析脚本**
  - 位置：项目根目录
  - 目标：分析市场参考价失败项，找出可优化的规则
  - 已打开：IDE中正在查看此文件（第21行）
  
- [ ] **提升断路器/漏保 auto_fill_rate（当前0%）**
  - 排查审核数据中具体条目的匹配路径
  - 可能需要在market_reference中新增更多断路器型号规则
  
- [ ] **提升电缆线缆 auto_fill_rate（当前6.67%）**
  - 复杂结构电缆（4大+1小、3大+2小）的自动填充
  - 需要为YJV等型号添加更精准的market_reference规则

#### 优先级：中
- [ ] **提升配管 auto_fill_rate（当前12.5%）**
  - 非标规格配管定价
  - 可能需要在market_reference中补充规则
  
- [ ] **提升material_aux指标（当前91.2%）**
  - 部分项目辅材计算逻辑仍有偏差
  - 重点关注mep_install中辅材计算公式

### 测试命令
```bash
# 回归测试（修改后必须运行）
python app.py regression

# 审计评估（查看核心指标）
python app.py audit-judge --limit 500

# 市场参考价失败项分析
python _market_ref_failures.py
```

### 关键文件索引
| 文件 | 作用 |
|------|------|
| `config/market_reference_prices.json` | 市场参考价规则库 |
| `config/settings.json` | 全局配置（auto_fill阈值等） |
| `src/pricing/component_judge.py` | 多源判断核心逻辑 |
| `src/pricing/mep_install_price.py` | 机电安装定价（电缆、配管、断路器等） |
| `src/pricing/market_reference.py` | 市场参考价匹配引擎 |
| `src/pricing/reconcile.py` | 合价校准逻辑 |

### 项目路径
- **工作目录**：`D:\projects\cost-estimation`
- **数据库**：`data/knowledge.db`
- **学习清单**：`清单数据资料/AI学习清单/`
- **招标清单**：`清单数据资料/甲方招标清单/`
- **成本分析**：`data/exports/`

### 注意事项
1. 所有修改后必须运行 `python app.py regression` 确保6套项目校准100%
2. 使用 `preserve_components: true` 锁定market_reference规则的分项参数，避免工艺拆分
3. 新增market_reference规则时必须添加`exclude_name_keywords`防止误匹配
4. 保持C盘旧路径兼容：`config/settings.json`中的路径可能需要检查

---
*此文档由会话自动生成，供AI上下文恢复使用*
