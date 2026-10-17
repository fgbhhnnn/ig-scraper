import json, os, sys, threading, http.server
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from igscraper import updater, __version__
import pytest

class R:
    def __init__(s, d): s.d = d
    def raise_for_status(s): pass
    def json(s): return s.d

def rel(tag, assets=True):
    return {'tag_name': tag, 'body': '- 修复', 'html_url': 'https://github.com/x',
            'assets': [{'name': 'Social-Scraper.exe', 'size': 123, 'browser_download_url': f'https://github.com/{updater.REPO}/releases/download/{tag}/Social-Scraper.exe'}] if assets else []}

def test_version_compare():
    assert updater.newer('v1.10.0', '1.9.9') and updater.newer('1.6.1', '1.6.0')
    assert not updater.newer('v1.6.0', '1.6.0') and not updater.newer('v1.5.9', '1.6.0')

def test_check_newer_and_same():
    d = updater.check(lambda u: R(rel('v99.0.0')))
    assert d['newer'] and d['latest'] == '99.0.0' and d['url'].endswith('Social-Scraper.exe') and d['notes'] == '- 修复'
    assert not updater.check(lambda u: R(rel('v' + __version__)))['newer']
    assert not updater.check(lambda u: R(rel('v99.0.0', assets=False)))['newer']   # no exe yet -> don't prompt

def test_download_url_whitelist(monkeypatch):
    monkeypatch.setattr(updater, 'exe_path', lambda: '/tmp/x.exe')
    with pytest.raises(RuntimeError): updater.start_download('https://evil.com/a.exe')

def test_download_and_mz_check(tmp_path, monkeypatch):
    body = b'MZ' + b'\0' * 5000
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(s):
            s.send_response(200); s.send_header('Content-Length', str(len(body))); s.end_headers(); s.wfile.write(body)
        def log_message(s, *a): pass
    srv = http.server.HTTPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(updater, '_proxies', lambda: None)
    dest = str(tmp_path / 'a.exe.new')
    updater._download(f'http://127.0.0.1:{srv.server_port}/f', dest)
    assert updater.ST['state'] == 'ready' and open(dest, 'rb').read() == body
    srv.shutdown()

def test_ps_script():
    s = updater.ps_script(r"C:\a b\测试 (x)\Social-Scraper (1).exe", [4321, 99])
    assert "$exe = 'C:\\a b\\测试 (x)\\Social-Scraper (1).exe'" in s and '@(4321,99)' in s and 'Wait-Process -Id $p -Timeout 30' in s
    assert 'Stop-Process -Id $p -Force' in s and "PYINSTALLER_RESET_ENVIRONMENT = '1'" in s and 'Start-Process -FilePath $exe' in s
    assert "update.log'" in s and 'LiteralPath' in s
    assert "'it''s'" == updater._psq("it's")

def test_api_routes(monkeypatch, tmp_path):
    monkeypatch.setenv('IGS_DATA_DIR', str(tmp_path))
    from igscraper import server
    monkeypatch.setattr(updater, 'check', lambda: {'current': __version__, 'latest': '9.9.9', 'newer': True, 'url': 'u', 'notes': '', 'page': '', 'size': 1, 'tag': 'v9.9.9'})
    c = server.app.test_client()
    d = c.get('/api/update/check').json
    assert d['ok'] and d['newer'] and not d['skipped'] and d['can_apply'] is False
    c.post('/api/update/skip', json={'version': '9.9.9'})
    assert c.get('/api/update/check').json['skipped']

def test_clean_env():
    e = updater.clean_env({'PATH': 'x', '_MEIPASS2': 'C:/t/_MEI1', '_PYI_APPLICATION_HOME_DIR': 'C:/t/_MEI1', '_PYI_PARENT_PROCESS_LEVEL': '1', '_PYI_ARCHIVE_FILE': 'a'})
    assert e == {'PATH': 'x', 'PYINSTALLER_RESET_ENVIRONMENT': '1'}

def test_local_url_only_with_flag(monkeypatch):
    monkeypatch.delenv('IGS_UPDATE_ALLOW_LOCAL', raising=False)
    assert not updater._allowed('http://127.0.0.1:8000/new.exe')
    monkeypatch.setenv('IGS_UPDATE_ALLOW_LOCAL', '1')
    assert updater._allowed('http://127.0.0.1:8000/new.exe') and not updater._allowed('http://evil.com/a.exe')
