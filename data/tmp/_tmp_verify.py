# -*- coding: utf-8 -*-
"""验证新打包 docx：完整性 + 第7/8节内容。"""
import sys, os, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tmp_docx_read as reader

DOCX = r"D:\工作\投标项目\珠海海德公馆会所项目-20260618\投标文件-20260819\物资投标-亿美佳\01 珠海丹田海德公馆项目 精装修材料-投标文件.docx"
OUT = r"d:\projects\cost-estimation\data\tmp\_tmp_verify_out.txt"

# 1) zip 完整性
zf = zipfile.ZipFile(DOCX)
bad = zf.testzip()
names = zf.namelist()
zf.close()
print("zip testzip:", "OK" if bad is None else f"BAD:{bad}")
print("entries:", len(names))
assert "word/document.xml" in names

# 2) 读取正文
reader.DOCX = DOCX
reader.OUT = OUT
import io
buf = io.StringIO()
_orig = sys.stdout
sys.stdout = buf
try:
    reader.main()
finally:
    sys.stdout = _orig
with open(OUT, "w", encoding="utf-8") as f:
    f.write(buf.getvalue())

# 3) 关键字检查
content = buf.getvalue()
checks = [
    "组织供应、运输、售后服务方案",
    "组织供应方案",
    "运输方案",
    "气候环境应对措施",
    "工期保障措施",
    "售后服务方案",
    "投标物资运达施工现场后的保护措施和要求",
    "卸货与堆放管理",
    "防潮防雨措施",
    "成品保护措施",
    "安全文明管理",
    "质量追溯与交接要求",
    "9．其他材料",
]
print("---- 关键字检查 ----")
for c in checks:
    print(("OK " if c in content else "MISSING ") + c)
print("---- 段落计数 ----")
items_count = content.split("TOTAL_ITEMS=")[-1].split()[0] if "TOTAL_ITEMS=" in content else "?"
print("items:", items_count)
print("---- 第7/8节顺序抽查 ----")
idx7 = content.find("7．组织供应、运输、售后服务方案")
idx7c = content.find("组织供应方案")
idx8 = content.find("8．投标物资运达施工现场后的保护措施和要求")
idx8c = content.find("卸货与堆放管理")
idx9 = content.find("9．其他材料")
order_ok = idx7 >= 0 and idx7c > idx7 and idx8 > idx7c and idx8c > idx8 and idx9 > idx8c
print("顺序OK" if order_ok else f"顺序异常: 7={idx7} 7c={idx7c} 8={idx8} 8c={idx8c} 9={idx9}")
