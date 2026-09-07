# -*- coding: utf-8 -*-
"""读取投标 docx 全文，定位 7/8 节内容并输出上下文。"""
import sys, zipfile, re
import xml.etree.ElementTree as ET

DOCX = sys.argv[1] if len(sys.argv) > 1 else r"D:\工作\投标项目\珠海海德公馆会所项目-20260618\投标文件-20260819\物资投标-亿美佳\01 珠海丹田海德公馆项目 精装修材料-投标文件.docx"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"d:\projects\cost-estimation\data\tmp\_tmp_docx_out.txt"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def para_text(p):
    """提取一个 w:p 内的所有文本（含 w:t、w:delText、w:tab、w:br）。"""
    parts = []
    for node in p.iter():
        tag = node.tag
        if tag in (W + "t", W + "delText"):
            parts.append(node.text or "")
        elif tag == W + "tab":
            parts.append("\t")
        elif tag == W + "br":
            parts.append("\n")
        elif tag == W + "drawing":
            parts.append("【图】")
        elif tag == W + "pict":
            parts.append("【图】")
    return "".join(parts)


def walk_body(body):
    """按文档顺序产出 (kind, elem, text)。"""
    for child in body:
        if child.tag == W + "p":
            yield ("p", child, para_text(child))
        elif child.tag == W + "tbl":
            yield ("tbl", child, "")
            for row in child.findall(W + "tr"):
                cells = []
                for tc in row.findall(W + "tc"):
                    txt = []
                    for p in tc.findall(W + "p"):
                        txt.append(para_text(p))
                    cells.append("|".join(txt))
                yield ("tr", row, " | ".join(cells))
        elif child.tag == W + "sdt":
            # 结构化文档标签，递归内容
            for sub in child.iter():
                if sub.tag == W + "p":
                    yield ("p", sub, para_text(sub))


def main():
    zf = zipfile.ZipFile(DOCX)
    xml = zf.read("word/document.xml").decode("utf-8")
    zf.close()
    root = ET.fromstring(xml)
    body = root.find(W + "body")
    items = list(walk_body(body))

    # 找目标标题
    targets = ["组织供应、运输、售后服务方案", "投标物资运达施工现场后的保护措施"]
    found = {}
    for i, (kind, elem, text) in enumerate(items):
        for t in targets:
            if t in text and t not in found:
                found[t] = i

    out = []
    for t, i in found.items():
        out.append("=" * 60)
        out.append(f"目标: {t}  定位段落#{i}")
        out.append("=" * 60)
        start = max(0, i - 3)
        end = min(len(items), i + 60)
        for j in range(start, end):
            kind, elem, text = items[j]
            if kind == "tr":
                out.append(f"[{j}][表格行] {text[:300]}")
            else:
                out.append(f"[{j}] {text[:300]}")
        out.append("")

    print("\n".join(out))
    print("TOTAL_ITEMS=", len(items))
    # 也打印所有段落的列表，帮助了解文档结构
    print("=" * 60)
    print("全部段落（仅含文字的段落，简化）")
    print("=" * 60)
    for j, (kind, elem, text) in enumerate(items):
        t = text.strip()
        if t and kind == "p":
            print(f"[{j}] {t[:120]}")


if __name__ == "__main__":
    import io
    buf = io.StringIO()
    _orig = sys.stdout
    sys.stdout = buf
    try:
        main()
    finally:
        sys.stdout = _orig
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    print("DONE")
