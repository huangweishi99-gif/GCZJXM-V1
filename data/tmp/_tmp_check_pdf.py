# -*- coding: utf-8 -*-
"""验证新导出的 PDF 中第8节内容"""
import io, os, re

LOG = r'd:\projects\cost-estimation\data\tmp\_tmp_check_pdf_out.txt'
PDF1 = r'D:\工作\投标项目\珠海海德公馆会所项目-20260618\投标文件-20260819\物资投标-亿美佳\01 珠海丹田海德公馆项目 精装修材料-投标文件-正本.pdf'
PDF2 = r'D:\工作\投标项目\珠海海德公馆会所项目-20260618\投标文件-20260819\物资投标-亿美佳\01 珠海丹田海德公馆项目 精装修材料-投标文件-副本.pdf'

buf = []
try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        buf.append('NO PDF LIB')
        with io.open(LOG, 'w', encoding='utf-8') as f:
            f.write('\n'.join(buf))
        raise SystemExit

KEYS = ['组织供应', '运输', '售后服务', '卸货与堆放管理', '防潮防雨',
        '成品保护措施', '安全文明管理', '质量追溯与交接要求']

for pdf in (PDF1, PDF2):
    try:
        r = PdfReader(pdf)
        n = len(r.pages)
        txt = '\n'.join((pg.extract_text() or '') for pg in r.pages)
        found = [k for k in KEYS if k in txt]
        missing = [k for k in KEYS if k not in txt]
        # 找 8． 标题所在页码
        page8 = -1
        for i, pg in enumerate(r.pages):
            t = pg.extract_text() or ''
            if '投标物资运达施工现场后的保护措施和要求' in t:
                page8 = i + 1
                break
        buf.append('%s | 页数=%d | 命中关键字=%d/%d | 缺:%s | 第8节标题页码=%s' % (
            os.path.basename(pdf), n, len(found), len(KEYS), missing, page8))
    except Exception as e:
        buf.append('%s | ERR %s' % (os.path.basename(pdf), e))

with io.open(LOG, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('DONE')
