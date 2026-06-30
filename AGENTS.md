# AGENTS.md — 智能清单组价系统

> **接手本项目请先读：`docs/PROJECT_HANDOFF.md`（目的、现状、下一步、命令）。**

## 项目是什么

本地化 **工程造价知识库 + 自动组价**：学习历史 Excel 清单，对招标清单匹配填价，**保留原招标 Excel 结构**追加成本列并同表去重链接。

**实务口径**：项目名称 = 做什么；项目特征 = 施工步骤；主材多在名称里。无机涂料 = 乳胶漆（套价/匹配同乳胶漆）。

**填价链**：整项历史 → 市场参考价 → 工艺价型（慎用）→ 主材规格价。见 `src/pricing/component_judge.py`、`docs/人材机判断机制.md`。

**ST/CT/WD 等编号**：仅为**该项目**物料书代号，不跨项目通用；见 `docs/项目石材与主材编号价库.md`。

**每次给资料**：`learn` 自动解剖 → 人材机 + 城市×档位价库 → `data/exports/解剖报告/`。

## 关键路径

| 路径 | 说明 |
|------|------|
| `docs/PROJECT_HANDOFF.md` | **交接规格（必读）** |
| `app.py` | CLI：`learn` `tender` `judge` `audit-judge` `sync` |
| `src/sync/api.py` | 手机同步 FastAPI 服务 |
| `mobile/index.html` | 手机 Web（PWA）校正界面 |
| `src/export/inplace_bidder.py` | 原表组价导出（默认交付） |
| `src/pricing/component_judge.py` | 人材机多源判断 |
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
python app.py external-price "墙面乳胶漆" --feature "..." --city 珠海
python app.py audit-judge

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
