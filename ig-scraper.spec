# -*- mode: python ; coding: utf-8 -*-
# 用法: pyinstaller ig-scraper.spec   -> dist/Social-Scraper(.exe)
from PyInstaller.utils.hooks import collect_data_files
import os
_sign = [('build_vendor/tiktok_sign/pure.py', 'tiktok_sign')] if os.path.exists('build_vendor/tiktok_sign/pure.py') else []
if not _sign: print('WARNING: TikTok signer not bundled (run tools/fetch_signer.py)')
try:
    import imageio_ffmpeg; _ff = [(imageio_ffmpeg.get_ffmpeg_exe(), 'ffmpeg')]
except Exception: _ff = []
if not _ff: print('WARNING: ffmpeg not bundled (pip install imageio-ffmpeg)')
a = Analysis(['run.py'], pathex=['.'], binaries=_ff, datas=[('igscraper/static', 'igscraper/static')] + collect_data_files('py3langid') + _sign,
             hiddenimports=['openpyxl', 'secrets', 'typing', 'hashlib', 'curl_cffi', 'curl_cffi.requests', 'py3langid', 'numpy'], excludes=['imageio_ffmpeg', 'tkinter', 'pandas', 'matplotlib'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='Social-Scraper', debug=False, strip=False, upx=False,
          console=False,  # 窗口模式：双击后不弹黑框，直接打开浏览器
          runtime_tmpdir=None)
