# -*- mode: python ; coding: utf-8 -*-
# 用法: pyinstaller ig-scraper.spec   -> dist/Social-Scraper(.exe)
a = Analysis(['run.py'], pathex=['.'], datas=[('igscraper/static', 'igscraper/static')],
             hiddenimports=['openpyxl'], excludes=['tkinter', 'numpy', 'pandas', 'matplotlib'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='Social-Scraper', debug=False, strip=False, upx=False,
          console=False,  # 窗口模式：双击后不弹黑框，直接打开浏览器
          runtime_tmpdir=None)
