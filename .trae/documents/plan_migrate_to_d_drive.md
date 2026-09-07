# 项目迁移到 D 盘执行计划

## 背景
用户要求将位于 `C:\Users\guangwan\Documents\工程造价项目-V1` 的项目完整迁移到 `D:\projects\cost-estimation`，并确保项目能继续顺利进行。

## 调研结果

### 代码路径分析
经过搜索和检查，项目中的路径引用情况如下：

1. **核心代码路径使用 ROOT 变量**：
   - `app.py`: `ROOT = Path(__file__).resolve().parent` (动态获取根目录)
   - `src/sync/config.py`: `ROOT = Path(__file__).resolve().parents[2]` (动态获取根目录)
   - `scripts/overnight_tick.py`: `ROOT = Path(__file__).resolve().parents[1]` (动态获取根目录)
   - 其他 Python 代码：均使用相对路径或 ROOT 变量，无硬编码 C 盘绝对路径

2. **配置文件使用相对路径**：
   - `config/settings.json`: `"database_path": "data/cost_pricing.db"` (相对路径)
   - `config/project_pairs.json`: 所有文件路径为相对路径

3. **存在硬编码绝对路径的文件**：
   - `scripts/extract_price_info.py`: 4 处硬编码 C 盘绝对路径 (第 78-81 行)
   - `README.md`: 命令示例中包含 C 盘路径 (仅文档，不影响运行)
   - `data/exports/*.json`: 历史报告中的绝对路径 (已生成文件，不影响运行)

## 执行步骤

### Step 1: 创建目标目录并复制项目
- 创建 `D:\projects\cost-estimation` 目录
- 使用 `robocopy` 或 `xcopy` 完整复制所有文件（包括隐藏文件和子目录）

### Step 2: 修改硬编码路径
修改 `scripts/extract_price_info.py` 中的 4 处绝对路径为基于 ROOT 的相对路径：
```python
# 修改前
pdf_path = r'C:\Users\guangwan\Documents\工程造价项目-V1\清单数据资料\...'
# 修改后
ROOT = Path(__file__).resolve().parents[1]
pdf_path = ROOT / "清单数据资料" / "AI学习清单" / "广联达定额" / "..."
```

### Step 3: 验证项目可用性
在新路径下执行以下验证：
```powershell
cd D:\projects\cost-estimation
pip install -r requirements.txt  # 确保依赖可用
python app.py regression  # 运行回归测试
python app.py audit-judge --limit 500 --no-export  # 运行审计
```

### Step 4: 更新文档中的路径（可选）
修改 README.md 和其他文档中的命令示例路径。

### Step 5: 清理 C 盘原项目目录
确认新路径项目运行正常后，删除 C 盘原目录（或保留为备份）。

## 注意事项
1. 项目数据库 `data/cost_pricing.db` 和 `data/knowledge.db` 需要完整复制
2. `清单数据资料/` 目录包含大量 Excel 样本文件，需要完整迁移
3. 如果 C 盘项目正被 IDE 占用，需要先关闭
4. 迁移后如果 Python 环境依赖路径配置，可能需要重新安装
