# 项目交接规格（PROJECT HANDOFF）

> **给下一个 AI / 开发者：先读本文 + `AGENTS.md`，再动代码。**  
> 存档日期：2026-05-27 · 仓库：https://github.com/huangweishi99-gif/GCZJXM-V1

---

## 1. 项目目的（一句话）

**本地化智能清单组价**：用历史项目 Excel（清单+成本拆解）建知识库，对甲方招标清单做「名称+特征+做法」匹配填价，**在原招标表上追加成本列导出**（格式不变、同表去重公式链接）。

---

## 2. 业务铁律（不可违背）

| 字段 | 含义 |
|------|------|
| **项目名称** | 做什么；主材品类多在名称里（完工可见面层） |
| **项目特征** | 施工工艺（逐条比对）；≈ 定额「工作内容」 |
| **组价** | 名称+特征**都**相似才整项套历史价；否则主材规格价或市场参考价 |

**定额口径（用户确认）**：

- **无机涂料 = 乳胶漆** → 套乳胶漆定额 / 查乳胶漆历史价（`src/normalize/paint_equiv.py`）。
- **清单单位 ≠ 定额单位**（如 100㎡ vs ㎡）→ 换算后再汇总。
- **门槛石** 清单单位常为 **m（延长米）**，不能按 ㎡ 中位数套价。

---

## 3. 当前已实现（截至存档）

| 能力 | 入口 / 模块 |
|------|-------------|
| 学习入库 + 解剖报告 | `python app.py learn` → `src/knowledge/anatomy.py` |
| 城市×档位价库 | `line_price_facts`, `material_price_facts` |
| 招标原表组价导出 | `tender --price --export` → `src/export/inplace_bidder.py` |
| 人材机多源判断 | `src/pricing/component_judge.py` |
| 市场参考价兜底 | `config/market_reference_prices.json` |
| 主材辅材目录 | `python app.py import-catalog` → `material_catalog` |
| 准确率回测 | `python app.py audit-judge` |
| 工艺价型库 | `craft_cost_profiles`（**勿盲目信高置信**，已加合理性校验） |

**乐晟样例输出**（本地生成，默认不进 Git）：  
`data/exports/1乐晟配套宿舍升级改造项目1号楼、2号楼-精装修硬装工程_组价_v3.xlsx`

**知识库**（本地生成）：`data/cost_pricing.db` — 用 `relearn-all` 可从 `清单数据资料/AI学习清单/` 重建。

---

## 4. 填价优先级（`component_judge`）

```text
① 历史整项（名称+特征+做法达标）
② 市场参考价 market_reference（深圳中档等）
③ 工艺价型 craft_profile（样本≥3、非 generic_finish、通过 sanity）
④ 主材价库 + 工艺份额模板
⑤ 不填 / 备注人工组价
```

自动填入阈值：`config/settings.json` → `component_judge.auto_fill_confidence`（默认 **0.8**）。

---

## 5. 目录地图

```text
app.py / ui.py              CLI / Streamlit
config/                     settings、feature_rules、market_reference、craft_trade_rules
src/ingest/                 表头识别、解析、综合单价分析块
src/match/                  精确/模糊/做法标签匹配
src/knowledge/              learn、价库、解剖、material_catalog
src/pricing/                组价、reference_resolve、component_judge、judge_audit
src/export/inplace_bidder.py  原表填价（核心交付）
docs/                       业务与流程文档（见下表）
清单数据资料/
  AI学习清单/               历史学习样本 + 主材辅材判定 + 广联达定额PDF(扫描)
  甲方招标清单/             招标样例（乐晟等）
data/cost_pricing.db        SQLite 知识库（本地重建）
data/exports/               组价导出、解剖报告、抽检报告（xlsx 多被 gitignore）
```

---

## 6. 文档索引（按主题）

| 文档 | 内容 |
|------|------|
| `docs/知识库解剖流程.md` | 每次 learn 必走流程 |
| `docs/项目特征与施工工艺.md` | 名称/特征/主材铁律 |
| `docs/清单定额与组价原理.md` | 清单vs定额、单位换算、无机涂料=乳胶漆 |
| `docs/人材机判断机制.md` | 多源判断 + audit-judge |
| `docs/主材与辅材识别原则.md` | 主辅材 + 判定表 |
| `docs/装饰工程施工工艺与定额套用.md` | 装饰工序要点 |
| `.cursor/rules/工程造价组价.mdc` | Cursor 编码约定 |

---

## 7. 常用命令（复制即用）

```powershell
pip install -r requirements.txt
python app.py init
python app.py import-catalog
python app.py relearn-all --reset          # 从 AI学习清单 重建知识库
python app.py backfill-kb                  # 重建价库/工艺价型

python app.py learn "清单数据资料/AI学习清单/某项目.xlsx" --city 深圳 --tier mid
python app.py tender "清单数据资料/甲方招标清单/招标.xlsx" --city 深圳 --tier mid --price --export

python app.py judge "项目名称" --feature "特征" --unit ㎡ --city 深圳 --tier mid
python app.py audit-judge                    # 批量回测准确率
python app.py stats
```

---

## 8. 已知问题与教训（audit-judge 结论）

- **工艺价型中位数**曾导致「高置信、低准确」（全库约 7% 核心准确）→ 已降权，**市场参考**优先。
- **广联达定额 PDF** 为扫描件，**未 OCR**，`quota_items` 表空 → 暂不能「特征→定额编号」自动套算。
- 新招标项目若大量项无历史匹配，依赖 `market_reference_prices.json` 维护质量。

---

## 9. 建议下一步（优先级）

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | 补 **深圳信息价/定额** 到 `market_reference_prices.json` | 乳胶漆、防水、门槛石、地砖等 |
| P0 | 持续 **learn** 深圳精装修历史表 | 提高整项匹配率，减少对市场参考依赖 |
| P1 | 广联达装饰册 **OCR → quota_items** | 特征推荐定额子目 |
| P1 | 扩充 `craft_trade_rules` / 减少 `generic_finish` | 降低工艺桶误判 |
| P2 | `audit-judge` 纳入 CI 或 learn 后自动跑 | 监控是否接近 80% 核心准确 |
| P2 | 机电安装专项工艺文档 + 规则 | 电缆、灯具、配电等 |

---

## 10. 修改代码时的检查清单

- [ ] 表头用 `detector.py`，不写死列号  
- [ ] 匹配改 `settings.json` + `match/engine.py` + 相关 docs  
- [ ] 新填价逻辑走 `component_judge`，勿绕过特征校验  
- [ ] 用户给新 Excel → `learn`（自动解剖），不是只改内存  
- [ ] 无机涂料项按乳胶漆等价处理  
- [ ] 不默认上传造价资料到云端  

---

## 11. 存档时 Git 约定

- **提交**：源码、`config/`、`docs/`、`.cursor/rules/`、样本资料路径下的 **xlsx/xls（学习清单）**。  
- **不提交**：`data/cost_pricing.db`、`data/exports/*.xlsx`（见 `.gitignore`），克隆后执行 `relearn-all` 与 `import-catalog` 恢复能力。
- **不提交**：`清单数据资料/.../广联达定额/*.pdf`（单文件>100MB，GitHub 限制）；请本地保留，OCR 后再提交结构化数据。

---

*本文随里程碑更新；重大行为变更请同步改 `AGENTS.md` 与本文件。*
