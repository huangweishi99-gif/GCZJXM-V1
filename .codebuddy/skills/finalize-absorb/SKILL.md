---
name: finalize-absorb
description: 用户确认项目成本数据已定稿时，自动执行闭环吸收——登记 project_pairs 金标准 → learn 入库（自动标 is_verified）→ 定稿优先聚合 → audit-judge 回归验证 → 报告回滚点。当用户说"定稿了/成本数据已确认/这版没问题了/吸收进数据库/学入这个定稿"时使用。禁止跳过回归静默入库。
---

# 定稿吸收标准（说"定稿"即触发）

## 触发语义

用户说「这个项目成本数据已经定稿 / 确认 / 这版没问题 / 吸收进数据库」→ 立即执行本流程，不再追问格式细节；只缺**文件路径/项目代号/城市**时才问。

## 执行流程（`scripts/absorb_final.py` 一键完成）

```
python absorb_final.py <定稿文件> --id <项目代号> --label <项目名> --city 深圳 --tier mid \
    [--quote-style metro_fitout] [--remark "口径说明"] [--dry-run] [--limit 500]
```

1. **登记 gold（先于 learn！）**：`config/project_pairs.json` 加/改 pair，`gold` 指向定稿文件。`is_verified` 在 learn 时按 gold 登记判定——顺序反了样本就不是定稿。
   - 项目已有 pair（如滨海 -3 版替换 -2 版）：**只改 gold 指向，旧版本样本一律保留**（定稿优先聚合自动让位；删旧样本实测会掉准确率——铁律）。
2. **备份**：`cost_pricing.db.bak_时间戳` + `project_pairs.json.bak_时间戳`。
3. **基线 audit**：`audit-judge --limit 500`（哈希抽样，池不变基线可比；limit>池自动全量），记录 core_main_and_labor / total_cost / auto_fill 指标。
4. **learn**：`app.py learn <文件> --name <label> --city <city> --tier <tier>`（路径自动 normcase 归一，重复学不会学成多个 project）。
5. **验证**：新 project 的 `cost_records.is_verified=1` 条数 >0（=0 说明 gold 未生效，停下查路径）。
6. **回归**：复跑 audit 与基线比对，**指标零变化才算吸收完成**；有回归打印回滚点并告知用户，不静默通过。

## 报告模板（吸收后必须给用户）

```
✅ 定稿吸收完成：<项目名>（project_id=N）
   学入成本记录 X 条，其中定稿样本(is_verified=1) Y 条
   基线 core/auto/total: ... → 吸收后: ...（零回归）
   回滚点: data/cost_pricing.db.bak_时间戳
```

## 红线

- 顺序铁律：先登记 gold → 再 learn → 再回归。
- 旧版本样本禁止删除；gold 只改指向。
- audit 指标从 `data/exports/audit_judge_summary.json` 读（stdout 同指标名出现多处，取 JSON 无歧义）。
- 回归非零 → 停，报告回滚点，等用户决策，不自动回滚。

## 脚本

- `scripts/absorb_final.py` — 上述全链路；`--dry-run` 看计划不写入；`--skip-audit` 仅调试用。
