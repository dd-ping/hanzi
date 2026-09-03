# -*- coding: utf-8 -*-
"""打包字库为单 zip，测量压缩收益"""
import os, zipfile, time
src = 'hanzi_data'
files = [f for f in os.listdir(src) if f.endswith('.json')]
total = sum(os.path.getsize(os.path.join(src, f)) for f in files)
print('文件数:%d 原始总大小:%.2fMB' % (len(files), total / 1024 / 1024))
t0 = time.time()
with zipfile.ZipFile('hanzi_data.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for f in files:
        z.write(os.path.join(src, f), f)
sz = os.path.getsize('hanzi_data.zip') / 1024 / 1024
print('打包zip耗时:%.1fs 压缩后:%.2fMB' % (time.time() - t0, sz))
