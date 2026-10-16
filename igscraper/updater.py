"""In-app auto update from public GitHub Releases (fgbhhnnn/ig-scraper)."""
import os, re, sys, threading, subprocess
from . import __version__
REPO = 'fgbhhnnn/ig-scraper'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
ASSET = 'Social-Scraper.exe'
ST = {'state': 'idle', 'got': 0, 'total': 0, 'error': '', 'path': ''}

def vtuple(v):
    return tuple(int(x) for x in re.findall(r'\d+', str(v or ''))[:3]) or (0,)

def newer(remote, local=__version__):
    return vtuple(remote) > vtuple(local)

def _proxies():
    try:
        from .tt import sys_proxies
        return sys_proxies()
    except Exception: return None

def check(get=None):
    import requests
    get = get or (lambda u: requests.get(u, timeout=15, proxies=_proxies(), headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Social-Scraper'}))
    r = get(API); r.raise_for_status(); d = r.json()
    tag = d.get('tag_name', '')
    url = next((a['browser_download_url'] for a in d.get('assets', []) if a.get('name') == ASSET), '')
    return {'current': __version__, 'latest': tag.lstrip('v'), 'tag': tag, 'newer': bool(url) and newer(tag),
            'notes': d.get('body') or '', 'url': url, 'page': d.get('html_url', ''),
            'size': next((a.get('size', 0) for a in d.get('assets', []) if a.get('name') == ASSET), 0)}

def exe_path():
    return sys.executable if getattr(sys, 'frozen', False) else ''

def _download(url, dest):
    import requests
    try:
        ST.update(state='downloading', got=0, total=0, error='', path='')
        with requests.get(url, stream=True, timeout=60, proxies=_proxies(), headers={'User-Agent': 'Social-Scraper'}) as r:
            r.raise_for_status(); ST['total'] = int(r.headers.get('content-length') or 0)
            with open(dest + '.part', 'wb') as f:
                for ch in r.iter_content(256 * 1024):
                    f.write(ch); ST['got'] += len(ch)
        if ST['total'] and ST['got'] != ST['total']: raise IOError('下载不完整')
        with open(dest + '.part', 'rb') as f:
            if f.read(2) != b'MZ': raise IOError('下载的文件不是有效的 exe')
        os.replace(dest + '.part', dest); ST.update(state='ready', path=dest)
    except Exception as e:
        ST.update(state='error', error=str(e))

def start_download(url):
    exe = exe_path()
    if not exe: raise RuntimeError('只有 exe 版本支持自动更新')
    if not str(url).startswith(f'https://github.com/{REPO}/releases/download/'): raise RuntimeError('下载地址不合法')
    if ST['state'] == 'downloading': return
    threading.Thread(target=_download, args=(url, exe + '.new'), daemon=True).start()

def bat_script(exe, pid):
    """Wait for this process to exit, swap exe (keep .old backup), restart. Rolls back if move fails."""
    name = os.path.basename(exe)
    return ('@echo off\r\nchcp 65001 >nul\r\n'
            f':w\r\ntasklist /FI "PID eq {pid}" | find "{pid}" >nul && (timeout /t 1 /nobreak >nul & goto w)\r\n'
            f'del /f /q "{exe}.old" 2>nul\r\n'
            f'move /y "{exe}" "{exe}.old" >nul || goto fail\r\n'
            f'move /y "{exe}.new" "{exe}" >nul || (move /y "{exe}.old" "{exe}" >nul & goto fail)\r\n'
            f'start "" "{exe}"\r\ngoto end\r\n'
            f':fail\r\nstart "" "{exe}"\r\n'
            f':end\r\ndel "%~f0"\r\n')

def apply():
    exe = exe_path()
    if ST['state'] != 'ready' or not exe or not os.path.exists(exe + '.new'): raise RuntimeError('新版本还没下载完成')
    bat = os.path.join(os.path.dirname(exe), '_update.bat')
    with open(bat, 'w', encoding='utf-8') as f: f.write(bat_script(exe, os.getpid()))
    subprocess.Popen(['cmd', '/c', bat], creationflags=0x08000000 | 0x00000008, close_fds=True)  # NO_WINDOW|DETACHED
    threading.Timer(0.8, lambda: os._exit(0)).start()
