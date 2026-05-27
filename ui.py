"""Streamlit 图形界面 — 智能清单组价。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent

from src.db.database import init_database
from src.export.excel import export_pricing_job
from src.knowledge.repository import KnowledgeRepository
from src.link.export_link import export_dedupe_workbook, export_linked_pricing
from src.pricing.engine import PricingEngine

st.set_page_config(page_title="智能清单组价", layout="wide")
st.title("智能清单组价系统")

init_database()

match_mode = st.sidebar.selectbox(
    "匹配模式",
    ["auto", "exact", "fuzzy"],
    format_func=lambda x: {"auto": "自动", "exact": "仅精确", "fuzzy": "含模糊"}[x],
)
st.sidebar.markdown(
    """
**精确**：名称≥98%、特征≥92%  
**模糊**：名称≥85%、特征≥75%  
**自动**：先精确后模糊

**去重链接**：相同名称+单位+做法只填母表一次，明细自动引用（吸收 lj.exe 思路）
"""
)

tab_learn, tab_tender, tab_dedupe, tab_match, tab_stats = st.tabs(
    ["学习入库", "招标组价", "去重链接", "匹配测试", "知识库"]
)

with tab_learn:
    st.subheader("导入新清单 + 价格（自主学习）")
    up = st.file_uploader("选择 Excel", type=["xlsx", "xls"], key="learn")
    pname = st.text_input("工程名称（可选）")
    if up and st.button("开始学习", type="primary"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(up.name).suffix) as tmp:
            tmp.write(up.getvalue())
            path = tmp.name
        repo = KnowledgeRepository()
        r = repo.learn_from_file(path, project_name=pname or None)
        st.success(json.dumps(r, ensure_ascii=False, indent=2))

with tab_tender:
    st.subheader("甲方招标清单 → 单价分析表")
    up2 = st.file_uploader("招标 Excel", type=["xlsx", "xls"], key="tender")
    tname = st.text_input("工程名称（可选）", key="tname")
    dedupe_link = st.checkbox(
        "去重链接导出（推荐大清单）",
        value=True,
        help="导出含「去重母表」Sheet，相同项成本只填一次，明细行公式自动链接",
    )
    if up2 and st.button("导入并组价导出", type="primary"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(up2.name).suffix) as tmp:
            tmp.write(up2.getvalue())
            path = tmp.name
        repo = KnowledgeRepository()
        imp = repo.import_tender(path, project_name=tname or None)
        eng = PricingEngine(match_mode=match_mode)
        pr = eng.run_for_project(imp["project_id"])
        out = export_pricing_job(pr["job_id"], use_dedupe_link=dedupe_link)
        st.success(f"组价完成：{json.dumps(pr, ensure_ascii=False)}")
        if dedupe_link:
            st.info("已含去重母表：请在「去重母表」Sheet 修改主材/人工等，明细行自动更新。")
        st.download_button(
            "下载单价分析表",
            data=Path(out).read_bytes(),
            file_name=Path(out).name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with tab_dedupe:
    st.subheader("清单去重 + 链接（不经过知识库）")
    st.caption("适合纯招标清单：先去重填价，再链接回全量表。去重键 = 名称 + 单位 + 做法。")

    mode = st.radio("操作", ["仅去重", "去重后链接"], horizontal=True)

    if mode == "仅去重":
        up_d = st.file_uploader("清单 Excel", type=["xlsx", "xls"], key="dedupe_only")
        if up_d and st.button("生成去重母表", type="primary"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(up_d.name).suffix) as tmp:
                tmp.write(up_d.getvalue())
                path = tmp.name
            out, items = export_dedupe_workbook(path)
            total = sum(i.line_count for i in items)
            st.success(f"{total} 行 → {len(items)} 个唯一项（少填 {total - len(items)} 行）")
            st.download_button(
                "下载去重母表",
                data=Path(out).read_bytes(),
                file_name=Path(out).name,
            )
    else:
        c1, c2 = st.columns(2)
        with c1:
            up_full = st.file_uploader("全量清单", type=["xlsx", "xls"], key="link_full")
        with c2:
            up_master = st.file_uploader("已填价的去重母表", type=["xlsx", "xls"], key="link_master")
        if up_full and up_master and st.button("生成链接组价表", type="primary"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as t1:
                t1.write(up_full.getvalue())
                p1 = t1.name
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as t2:
                t2.write(up_master.getvalue())
                p2 = t2.name
            out = export_linked_pricing(p1, p2)
            st.success(f"已生成链接表: {out.name}")
            st.download_button("下载链接组价表", data=Path(out).read_bytes(), file_name=Path(out).name)

with tab_match:
    st.subheader("相同项匹配测试")
    c1, c2, c3 = st.columns(3)
    with c1:
        mn = st.text_input("项目名称", value="轻钢龙骨隔墙（100mm）")
    with c2:
        mf = st.text_area("项目特征", height=80)
    with c3:
        mu = st.text_input("单位", value="㎡")
    if st.button("搜索匹配"):
        eng = PricingEngine(match_mode=match_mode)
        rows = eng.search(mn, mf, mu)
        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.warning("无匹配（检查单位或与库内是否一致）")

with tab_stats:
    repo = KnowledgeRepository()
    st.json(repo.stats())
    st.write("样本最多的标准项：")
    for row in repo.list_standard_items(15):
        st.text(f"[{row['sample_count']}] {row['name_norm']} | {row['unit_norm']}")
