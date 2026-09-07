# -*- coding: utf-8 -*-
import io, sys
sys.path.insert(0, r'd:\projects\cost-estimation')
p = r'data\tmp\_tmp_door_dump_out.txt'
t = io.open(p, encoding='utf-8').read()
blocks = t.split('[')
ok = sum(1 for b in blocks if b.startswith('OK  '))
fails = sum(1 for b in blocks if b.startswith('FAIL'))
print(f'OK={ok} FAIL={fails} total={ok+fails}')
for b in blocks:
    if b.startswith('FAIL'):
        print('[' + b.split('\n')[0].strip())
