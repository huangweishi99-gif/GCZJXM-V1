# -*- coding: utf-8 -*-
"""招标清单"可投标性体检"：五要素完整性 + 常见废标雷区。

体检项：
1. 项目编码：12 位国标清单编码（前 9 位规范 + 3 位自定），缺失/位数不足/含字母 → 雷区
2. 项目名称：缺失/过短
3. 项目特征：缺失（规范要求描述做法、材质、规格）
4. 计量单位：缺失/异常单位（"项/宗"等计价单位需提示）
5. 工程量：缺失/为 0/为负（废标雷区）

输出：按 致命/警告/提示 分级报告，供 `validate-boq` 命令使用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.ingest.parser import parse_workbook
from src.ingest.line_types import cell_str

# 异常/需提示的计量单位
SUSPICIOUS_UNITS = {"项", "宗", "批", "包", "系统", "组"}
# 合法编码：12 位（前 9 位国标数字 + 3 位自定）；
# 补充/变更清单项：前 9 位国标数字 + 字母 + 数字（如 011302B003001，广联达补充清单格式），仅提示
CODE_RE = re.compile(r"^[0-9]{12}$")
# 补充/变更清单项：以数字开头、含字母（广联达 011302B003001 等格式），仅提示
CODE_RE_ALPHA = re.compile(r"^[0-9]+[A-Za-z]")


@dataclass
class BoqIssue:
    level: str  # fatal / warning / info
    kind: str  # code / name / feature / unit / quantity
    seq: str
    name: str
    message: str


@dataclass
class BoqValidationReport:
    file_path: str
    project_name: str
    total_lines: int
    valid_lines: int = 0
    issues: List[BoqIssue] = field(default_factory=list)

    @property
    def fatal_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "fatal")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "warning")

    @property
    def pass_rate(self) -> float:
        if not self.total_lines:
            return 0.0
        return round(self.valid_lines / self.total_lines * 100, 1)


def validate_boq(path: str) -> BoqValidationReport:
    """解析招标清单并逐行体检。"""
    wb = parse_workbook(path)
    report = BoqValidationReport(
        file_path=str(path),
        project_name=wb.project_name,
        total_lines=len(wb.lines),
    )

    for ln in wb.lines:
        name = cell_str(ln.name)
        code = cell_str(ln.list_code)
        feature = cell_str(ln.feature)
        unit = cell_str(ln.unit)

        line_ok = True
        line_issues: List[BoqIssue] = []

        # 1. 项目编码
        if not code:
            line_issues.append(BoqIssue("warning", "code", ln.seq, name or "(无名)", "项目编码缺失"))
            line_ok = False
        elif not CODE_RE.match(code):
            if CODE_RE_ALPHA.match(code):
                # 含字母=补充/变更清单项，仅提示
                line_issues.append(BoqIssue(
                    "info", "code", ln.seq, name or "(无名)",
                    f"项目编码[{code}]为补充清单项（含字母），请核实 12 位国标编码",
                ))
            else:
                line_issues.append(BoqIssue(
                    "warning", "code", ln.seq, name or "(无名)",
                    f"项目编码[{code}]非法：应为 9~12 位数字（国标 9 位 + 自定 3 位）",
                ))
                line_ok = False

        # 2. 项目名称
        if not name:
            line_issues.append(BoqIssue("fatal", "name", ln.seq, "(无名)", "项目名称缺失"))
            line_ok = False
        elif len(name) < 2:
            line_issues.append(BoqIssue("warning", "name", ln.seq, name, "项目名称过短，疑似非法行"))
            line_ok = False

        # 3. 项目特征（清单计价规范：特征描述是组价依据，缺失易引起歧义）
        if not feature:
            line_issues.append(BoqIssue(
                "warning", "feature", ln.seq, name or "(无名)", "项目特征缺失（无做法/材质/规格描述）",
            ))

        # 4. 计量单位
        if not unit:
            line_issues.append(BoqIssue("fatal", "unit", ln.seq, name or "(无名)", "计量单位缺失"))
            line_ok = False
        elif unit in SUSPICIOUS_UNITS:
            line_issues.append(BoqIssue(
                "info", "unit", ln.seq, name or "(无名)",
                f"计量单位[{unit}]为计价单位而非计量单位，请核实清单规范",
            ))

        # 5. 工程量
        qty = ln.quantity
        if qty is None:
            line_issues.append(BoqIssue("fatal", "quantity", ln.seq, name or "(无名)", "工程量缺失"))
            line_ok = False
        elif qty <= 0:
            line_issues.append(BoqIssue(
                "fatal", "quantity", ln.seq, name or "(无名)",
                f"工程量 {qty} 为 0 或负值（废标雷区）",
            ))
            line_ok = False

        if line_ok:
            report.valid_lines += 1
        report.issues.extend(line_issues)

    # 排序：fatal 优先
    level_order = {"fatal": 0, "warning": 1, "info": 2}
    report.issues.sort(key=lambda i: level_order.get(i.level, 3))
    return report


def format_report(report: BoqValidationReport) -> str:
    """把体检报告格式化为文本。"""
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append(f"招标清单体检报告")
    lines.append(f"文件：{report.file_path}")
    lines.append(f"项目：{report.project_name}")
    info_count = sum(1 for i in report.issues if i.level == "info")
    lines.append(f"清单行数：{report.total_lines}，通过：{report.valid_lines}，通过率：{report.pass_rate}%")
    lines.append(f"致命问题：{report.fatal_count}，警告：{report.warning_count}，提示：{info_count}")
    lines.append("=" * 60)

    if not report.issues:
        lines.append("✓ 全部通过，未发现废标雷区。")
        return "\n".join(lines)

    shown = 0
    for iss in report.issues:
        if shown >= 80:
            lines.append(f"... 其余 {len(report.issues) - shown} 条省略，详见完整输出")
            break
        tag = {"fatal": "致命", "warning": "警告", "info": "提示"}[iss.level]
        lines.append(f"[{tag}] 序号{iss.seq or '-'} {iss.name[:40] or '(无名)'}：{iss.message}")
        shown += 1

    return "\n".join(lines)
