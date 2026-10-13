"""TikTok web request signing glue.

The signature primitives (X-Dynosaur / X-Gnarly) come from `signing/pure.py` of
cv-cat/TiktokApis (https://github.com/cv-cat/TiktokApis), credit to its author. The file
is NOT committed to this repository; the build downloads it at a pinned commit, verifies
its SHA-256 (tools/fetch_signer.py) and bundles it into the exe. At runtime a copy in the
data dir (downloaded/selected by the user, for updates) takes priority over the bundled one. The file only
uses the Python standard library, so it runs inside the packaged exe (no Node/Python).
"""
import hashlib, importlib.util, os, time, urllib.parse, requests
from .paths import data_dir

PURE_COMMIT = 'b3b2a448800e4ca9e061203b9ba1f53d1d6d3082'
PURE_URL = f'https://raw.githubusercontent.com/cv-cat/TiktokApis/{PURE_COMMIT}/signing/pure.py'
PURE_SHA256 = '74326dada4b64cfadd466a39e514eacd8eaa53fa2f9af3c14f771ae8d16c067d'
_mod = None

import sys
def pure_path(): return os.path.join(data_dir(), 'tiktok_sign', 'pure.py')
def bundled_path():
    base = getattr(sys, '_MEIPASS', None) or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build_vendor')
    return os.path.join(base, 'tiktok_sign', 'pure.py')
def active_path():
    """User copy in data dir (updates) > bundled copy."""
    for p, src in ((pure_path(), 'user'), (bundled_path(), 'bundled')):
        if os.path.exists(p): return p, src
    return None, None

def status():
    p, src = active_path()
    if not p: return {'ok': False, 'bundled': False, 'msg': '未找到 TikTok 签名模块：请点击「更新签名模块（可选）」下载'}
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    ver = '固定版本 b3b2a44，已校验' if h == PURE_SHA256 else f'自定义版本 {h[:8]}，未校验'
    msg = f'✅ 已内置 TikTok 签名模块（{ver}）' if src == 'bundled' else f'✅ 使用本地更新的签名模块（{ver}）'
    return {'ok': True, 'bundled': os.path.exists(bundled_path()), 'source': src, 'msg': msg, 'sha256': h}

def install(content=None):
    """Download the pinned file from GitHub (content=None) or install user-supplied bytes."""
    global _mod
    verify = content is None
    if content is None:
        r = requests.get(PURE_URL, timeout=30); r.raise_for_status(); content = r.content
    if verify and hashlib.sha256(content).hexdigest() != PURE_SHA256:
        raise RuntimeError('下载的签名模块校验失败（SHA-256 不一致）')
    if b'encode_gnarly_current' not in content or b'encode_dynosaur_current' not in content:
        raise RuntimeError('文件不是 TiktokApis 的 signing/pure.py')
    os.makedirs(os.path.dirname(pure_path()), exist_ok=True)
    with open(pure_path(), 'wb') as f: f.write(content)
    _mod = None
    return status()

def _load():
    global _mod
    if _mod is None:
        p, _ = active_path()
        if not p:
            raise RuntimeError('缺少 TikTok 签名模块：请在「Cookie」页 TikTok 区域点击「更新签名模块（可选）」')
        spec = importlib.util.spec_from_file_location('tt_pure_runtime', p)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); _mod = m
    return _mod

def signed_url(path, base_query, ms_token, ua, referer):
    """Return full URL with X-Dynosaur, msToken, X-Bogus(=1), X-Gnarly appended (browser order)."""
    P = _load()
    ts = int(time.time()); ms = time.time_ns() // 1_000_000
    ref = urllib.parse.urlsplit(referer); page = ref.netloc + (ref.path or '/')
    rand_b = 100_000_000 + (P._hash_url_state(base_query) % 900_000_000)
    d = hashlib.sha256((base_query + '|' + ua).encode()).digest()
    f8 = str(1_000_000_000 + int.from_bytes(d[:4], 'big') % 3_000_000_000)
    dy = P.encode_dynosaur_current(base_query, ua, page=page, timestamp=ts, rand_b=rand_b, runtime_field8=f8,
                                   runtime_field18='1.0.0.2870', runtime_field19=hashlib.md5((ua + '|' + page).encode()).hexdigest())
    gn = P.encode_gnarly_current(f'{base_query}&X-Dynosaur={dy}&msToken={ms_token}', '', ua, timestamp=ts, timestamp_ms=ms)
    q = lambda x: urllib.parse.quote(x, safe='')
    return f'https://www.tiktok.com{path}?{base_query}&X-Dynosaur={q(dy)}&msToken={ms_token}&X-Bogus=1&X-Gnarly={q(gn)}'
