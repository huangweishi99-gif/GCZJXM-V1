# -*- coding: utf-8 -*-
"""列出投标目录最终文件状态"""
import io, os, datetime

DIR = r'D:\工作\投标项目\珠海海德公馆会所项目-20260618\投标文件-20260819\物资投标-亿美佳'
OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_sec8_packed_out.txt'

buf = []
for name in sorted(os.listdir(DIR)):
    full = os.path.join(DIR, name)
    st = os.stat(full)
    mt = datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    buf.append('%-70s %10d  %s' % (name, st.st_size, mt))

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('OK')
