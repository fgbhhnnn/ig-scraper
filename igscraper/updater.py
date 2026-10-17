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

def _psq(x): return "'" + str(x).replace("'", "''") + "'"

def ps_script(exe, pids):
    """PowerShell 更新脚本（隐藏窗口运行）：-LiteralPath 处理空格/括号/中文路径；等待旧进程最多 30 秒，超时强制结束；
    重试替换 exe（保留 .old，失败回滚）；清掉 PyInstaller 运行时变量后启动新版；全程写 update.log。"""
    import ntpath   # 脚本只在 Windows 上运行
    d = ntpath.dirname(exe); log = ntpath.join(d, 'update.log')
    return '\r\n'.join([
        "$ErrorActionPreference = 'Continue'",
        f"$exe = {_psq(exe)}; $dir = {_psq(d)}; $log = {_psq(log)}",
        "function L($m) { try { Add-Content -LiteralPath $log -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $m) -Encoding UTF8 } catch {} }",
        f"$pids = @({','.join(str(int(p)) for p in pids)})",
        "L ('更新脚本开始，等待旧进程退出：' + ($pids -join ','))",
        "foreach ($p in $pids) { try { Wait-Process -Id $p -Timeout 30 -ErrorAction Stop } catch {} ;"
        " if (Get-Process -Id $p -ErrorAction SilentlyContinue) { L ('进程 ' + $p + ' 30 秒未退出，强制结束'); Stop-Process -Id $p -Force -ErrorAction SilentlyContinue; Start-Sleep 2 } }",
        "Start-Sleep -Milliseconds 1500",
        "Remove-Item -LiteralPath ($exe + '.old') -Force -ErrorAction SilentlyContinue",
        "$moved = $false",
        "for ($i = 0; $i -lt 30 -and -not $moved; $i++) { try { Move-Item -LiteralPath $exe -Destination ($exe + '.old') -Force -ErrorAction Stop; $moved = $true } catch { Start-Sleep 1 } }",
        "if ($moved) { try { Move-Item -LiteralPath ($exe + '.new') -Destination $exe -Force -ErrorAction Stop; L '已替换为新版本' }"
        " catch { L ('替换失败，回滚：' + $_); Move-Item -LiteralPath ($exe + '.old') -Destination $exe -Force -ErrorAction SilentlyContinue } }",
        "else { L '无法移动旧 exe（可能被占用或被杀毒软件锁定），继续使用旧版本' }",
        "try { Unblock-File -LiteralPath $exe -ErrorAction SilentlyContinue } catch {}",
        "foreach ($k in @('_MEIPASS2','_PYI_APPLICATION_HOME_DIR','_PYI_ARCHIVE_FILE','_PYI_PARENT_PROCESS_LEVEL','_PYI_SPLASH_IPC')) { Remove-Item -LiteralPath ('Env:' + $k) -ErrorAction SilentlyContinue }",
        "$env:PYINSTALLER_RESET_ENVIRONMENT = '1'",
        "try { Start-Process -FilePath $exe -WorkingDirectory $dir; L '已启动程序' } catch { L ('启动失败：' + $_) }",
        "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue",
        ''])

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
    for p in (exe + '.old', os.path.join(os.path.dirname(exe), '_update.bat'), os.path.join(os.path.dirname(exe), '_update.ps1')):
        for _ in range(5):
            try:
                if os.path.exists(p): os.remove(p); ulog(f'已清理 {os.path.basename(p)}')
                break
            except Exception: time.sleep(1)

def apply():
    exe = exe_path()
    if ST['state'] != 'ready' or not exe or not os.path.exists(exe + '.new'): raise RuntimeError('新版本还没下载完成')
    script = os.path.join(os.path.dirname(exe), '_update.ps1')
    pids = [os.getpid()]
    try:
        pp = os.getppid()
        if pp and pp != os.getpid(): pids.append(pp)   # onefile：引导父进程也持有 exe 文件锁
    except Exception: pass
    with open(script, 'w', encoding='utf-8-sig') as f: f.write(ps_script(exe, pids))   # BOM：Windows PowerShell 5 才能正确读中文
    ulog(f'开始更新：当前 {__version__}，等待进程 {pids}')
    cmd = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', script]
    # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP (+ BREAKAWAY_FROM_JOB)：不弹黑框，旧程序退出时不连带结束脚本
    flags = 0x08000000 | 0x00000200
    try: subprocess.Popen(cmd, creationflags=flags | 0x01000000, close_fds=True, env=clean_env(), cwd=os.path.dirname(exe))
    except OSError: subprocess.Popen(cmd, creationflags=flags, close_fds=True, env=clean_env(), cwd=os.path.dirname(exe))
    threading.Timer(0.8, lambda: os._exit(0)).start()
