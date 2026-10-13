# -*- mode: python ; coding: utf-8 -*-
# 用法: pyinstaller ig-scraper.spec   -> dist/Social-Scraper(.exe)
from PyInstaller.utils.hooks import collect_data_files
a = Analysis(['run.py'], pathex=['.'], datas=[('igscraper/static', 'igscraper/static')] + collect_data_files('py3langid'),
             hiddenimports=['openpyxl', 'secrets', 'typing', 'hashlib', 'curl_cffi', 'curl_cffi.requests', 'py3langid', 'numpy'], excludes=['tkinter', 'pandas', 'matplotlib'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='Social-Scraper', debug=False, strip=False, upx=False,
          console=False,  # 窗口模式：双击后不弹黑框，直接打开浏览器
          runtime_tmpdir=None)
