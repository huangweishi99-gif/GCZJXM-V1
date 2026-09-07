# -*- coding: utf-8 -*-
"""查看 data/exports 下的 audit 相关文件及时间戳"""
import io, os, datetime

DIR = r'd:\projects\cost-estimation\data\exports'
OUT = r'd:\projects\cost-estimation\data\tmp\_tmp_check_audit_files_out.txt'

buf = []
for name in sorted(os.listdir(DIR)):
    if 'audit' in name.lower() or '抽检' in name or 'audit' in name.lower():
        full = os.path.join(DIR, name)
        st = os.stat(full)
        mt = datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        buf.append('%-80s %10d  %s' % (name, st.st_size, mt))

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(buf))
print('done')
