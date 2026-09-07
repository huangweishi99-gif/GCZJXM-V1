# -*- coding: utf-8 -*-
"""用 Word COM 从最新主文件重新导出正本+副本 PDF"""
import os, io, time
import win32com.client

MAIN = r'D:\工作\投标项目\珠海海德公馆会所项目-20260618\投标文件-20260819\物资投标-亿美佳\01 珠海丹田海德公馆项目 精装修材料-投标文件.docx'
PDF1 = r'D:\工作\投标项目\珠海海德公馆会所项目-20260618\投标文件-20260819\物资投标-亿美佳\01 珠海丹田海德公馆项目 精装修材料-投标文件-正本.pdf'
PDF2 = r'D:\工作\投标项目\珠海海德公馆会所项目-20260618\投标文件-20260819\物资投标-亿美佳\01 珠海丹田海德公馆项目 精装修材料-投标文件-副本.pdf'
LOG = r'd:\projects\cost-estimation\data\tmp\_tmp_export_pdf_out.txt'

buf = []
word = None
try:
    word = win32com.client.DispatchEx('Word.Application')
    word.Visible = False
    word.DisplayAlerts = 0
    for pdf in (PDF1, PDF2):
        doc = None
        try:
            doc = word.Documents.Open(MAIN, ReadOnly=True)
            doc.ExportAsFixedFormat(pdf, 17)  # 17 = wdExportFormatPDF
            doc.Close(False)
            doc = None
            sz = os.path.getsize(pdf)
            st = time.localtime(os.path.getmtime(pdf))
            buf.append('OK %s | %d bytes | %s' % (os.path.basename(pdf), sz,
                        time.strftime('%Y-%m-%d %H:%M:%S', st)))
        except Exception as e:
            buf.append('ERR %s: %s' % (os.path.basename(pdf), e))
            if doc is not None:
                try: doc.Close(False)
                except: pass
finally:
    if word is not None:
        try: word.Quit()
        except: pass

with io.open(LOG, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('DONE')
