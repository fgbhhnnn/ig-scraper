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

def _allowed(url):
    if str(url).startswith(f'https://github.com/{REPO}/releases/download/'): return True
    # 仅供自动化测试（GitHub Actions 里的 Windows 端到端更新测试）使用本机地址
    return os.environ.get('IGS_UPDATE_ALLOW_LOCAL') == '1' and str(url).startswith('http://127.0.0.1:')

def start_download(url):
    exe = exe_path()
    if not exe: raise RuntimeError('只有 exe 版本支持自动更新')
    if not _allowed(url): raise RuntimeError('下载地址不合法')
    if ST['state'] == 'downloading': return
    threading.Thread(target=_download, args=(url, exe + '.new'), daemon=True).start()

def log_path(exe=None):
    exe = exe or exe_path()
    return os.path.join(os.path.dirname(exe), 'update.log') if exe else ''

def ulog(msg, exe=None):
    p = log_path(exe)
    if not p: return
    try:
        import time
        with open(p, 'a', encoding='utf-8') as f: f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + str(msg) + '\n')
    except Exception: pass

def bat_script(exe, pids):
    """等旧进程（onefile 的子进程 + 引导父进程）全部退出 → 重试替换 exe（保留 .old，失败回滚）→ 用干净环境启动新版 → 写 update.log。"""
    import ntpath   # 脚本只在 Windows 上运行
    d = ntpath.dirname(exe); log = ntpath.join(d, 'update.log')
    L = lambda m: f'echo %date% %time% {m}>>"{log}"\r\n'
    wait = ''.join(f':w{p}\r\nset /a n+=1\r\nif %n% gtr 120 goto waited\r\n'
                   f'tasklist /NH /FI "PID eq {p}" 2>nul | find " {p} " >nul && (ping -n 2 127.0.0.1 >nul & goto w{p})\r\n' for p in pids)
    return ('@echo off\r\nchcp 65001 >nul\r\nsetlocal\r\n'
            # 不要继承旧进程的 PyInstaller 运行时变量，否则新 exe 会去用旧的（已删除的）_MEI 临时目录而启动失败
            'set PYINSTALLER_RESET_ENVIRONMENT=1\r\nset _MEIPASS2=\r\nset _PYI_APPLICATION_HOME_DIR=\r\nset _PYI_ARCHIVE_FILE=\r\n'
            'set _PYI_PARENT_PROCESS_LEVEL=\r\nset _PYI_SPLASH_IPC=\r\nset _PYI_LINUX_PROCESS_NAME=\r\n'
            + L('更新脚本开始，等待旧进程退出') + 'set n=0\r\n' + wait + ':waited\r\n' + L('旧进程已退出（或等待超时）')
            + 'ping -n 3 127.0.0.1 >nul\r\n'
            f'del /f /q "{exe}.old" 2>nul\r\nset t=0\r\n'
            f':mv\r\nmove /y "{exe}" "{exe}.old" >nul 2>&1 && goto mv2\r\nset /a t+=1\r\n'
            f'if %t% geq 30 (' + L('无法移动旧 exe（可能被占用或被杀毒软件锁定）').rstrip('\r\n') + ' & goto start)\r\nping -n 2 127.0.0.1 >nul\r\ngoto mv\r\n'
            f':mv2\r\nmove /y "{exe}.new" "{exe}" >nul 2>&1 && (' + L('已替换为新版本').rstrip('\r\n') + ' & goto start)\r\n'
            f'move /y "{exe}.old" "{exe}" >nul 2>&1\r\n' + L('替换失败，已回滚旧版本')
            + f':start\r\n' + L('启动程序') + f'start "" /D "{d}" "{exe}"\r\n'
            'endlocal\r\n(goto) 2>nul & del "%~f0"\r\n')

def clean_env(env=None):
    e = dict(os.environ if env is None else env)
    for k in list(e):
        if k.startswith('_PYI_') or k in ('_MEIPASS2', '_MEIPASS'): e.pop(k)
    e['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return e

def startup_cleanup():
    """新版本启动后：删掉 .old 备份和残留的更新脚本"""
    exe = exe_path()
    if not exe: return
    import time
    for p in (exe + '.old', os.path.join(os.path.dirname(exe), '_update.bat')):
        for _ in range(5):
            try:
                if os.path.exists(p): os.remove(p); ulog(f'已清理 {os.path.basename(p)}')
                break
            except Exception: time.sleep(1)

def apply():
    exe = exe_path()
    if ST['state'] != 'ready' or not exe or not os.path.exists(exe + '.new'): raise RuntimeError('新版本还没下载完成')
    bat = os.path.join(os.path.dirname(exe), '_update.bat')
    pids = [os.getpid()]
    try:
        pp = os.getppid()
        if pp and pp != os.getpid(): pids.append(pp)   # onefile：引导父进程也持有 exe 文件锁
    except Exception: pass
    with open(bat, 'w', encoding='utf-8') as f: f.write(bat_script(exe, pids))
    ulog(f'开始更新：当前 {__version__}，等待进程 {pids}')
    # CREATE_NO_WINDOW（不要 DETACHED_PROCESS：那样 tasklist/ping 等控制台程序会各自弹出可见黑框）
    # CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB：旧程序退出时不连带结束更新脚本
    flags = 0x08000000 | 0x00000200
    try: subprocess.Popen(['cmd', '/c', bat], creationflags=flags | 0x01000000, close_fds=True, env=clean_env(), cwd=os.path.dirname(exe))
    except OSError: subprocess.Popen(['cmd', '/c', bat], creationflags=flags, close_fds=True, env=clean_env(), cwd=os.path.dirname(exe))
    threading.Timer(0.8, lambda: os._exit(0)).start()
