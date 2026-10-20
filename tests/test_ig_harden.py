import pytest
from igscraper import ig as I
from igscraper.ig import IG, Blocked

def test_profile_uid_html():
    assert I.parse_profile_uid('x "profile_id":"45322071413" y "is_private":false') == ('45322071413', False)
    assert I.parse_profile_uid('<meta content="profilePage_123">')[0] == '123'
    assert I.parse_profile_uid('{"id":"77","full_name":"a","username":"bob"}', 'bob')[0] == '77'
    assert I.parse_profile_uid('<html>nothing</html>', 'bob') == ('', None)

def test_cookie_set():
    ck, ch = I.cookie_set('sessionid=s; csrftoken=old; ds_user_id=1', {'csrftoken': 'new', 'rur': '"NCG\\0541"', 'evil': 'x', 'sessionid': '""'})
    assert ch and 'csrftoken=new' in ck and 'rur=NCG' in ck and 'evil' not in ck and 'sessionid=s' in ck
    assert I.cookie_set(ck, {'csrftoken': 'new'})[1] is False

def test_web_headers():
    h = I.web_headers('csrftoken=abc; sessionid=s', 'https://www.instagram.com/u/followers/', 'hmac.X')
    assert h['X-CSRFToken'] == 'abc' and h['X-IG-WWW-Claim'] == 'hmac.X' and h['X-IG-App-ID'] == I.APP_ID
    assert h['X-ASBD-ID'] and h['Referer'].endswith('/followers/') and h['X-Requested-With'] == 'XMLHttpRequest'

def test_blocked_reason():
    assert '429' in I.blocked_reason(429, '') and '1~2 小时' in I.blocked_reason(429, '')
    assert '稍等' in I.blocked_reason(401, '{"message":"Please wait a few minutes before you try again."}')
    assert 'challenge' in I.blocked_reason(200, '', 'https://www.instagram.com/challenge/x')
    assert I.blocked_reason(200, '{"users":[]}') == ''

class R:
    def __init__(s, st, txt='{}', hdr=None, ck=None):
        s.status_code, s.text, s.headers, s.cookies = st, txt, hdr or {}, ck or {}
    def json(s):
        import json; return json.loads(s.text)
class S:
    def __init__(s, rs): s.rs = rs; s.headers = {'X-IG-App-ID': I.APP_ID}; s.cookies = {}; s.sent = []
    def get(s, url, **kw): s.sent.append(kw.get('headers')); return s.rs.pop(0)

def mk(rs):
    saved = []
    c = IG('sessionid=s; csrftoken=old; ds_user_id=1', 0, 0, lambda *a: None, on_cookie=saved.append)
    c._cs = S(rs); return c, saved

def test_api_refresh_claim_and_persist():
    c, saved = mk([R(200, '{"users":[]}', {'x-ig-set-www-claim': 'hmac.A'}, {'csrftoken': 'new'}), R(200, '{}')])
    st, o, _ = c.api('/api/v1/friendships/1/followers/', ref='r')
    assert st == 200 and o == {'users': []} and saved and 'csrftoken=new' in saved[-1]
    c.api('/x')
    h = c._cs.sent[-1]
    assert h['X-IG-WWW-Claim'] == 'hmac.A' and h['X-CSRFToken'] == 'new' and 'csrftoken=new' in h['Cookie']

@pytest.mark.parametrize('r', [R(429, ''), R(401, '{"message":"Please wait a few minutes"}'), R(403, '{}'), R(302, '', {'Location': '/accounts/login/'})])
def test_api_stops(r):
    c, _ = mk([r])
    with pytest.raises(Blocked): c.api('/x')

def test_get_429_no_retry(monkeypatch):
    c, _ = mk([])
    calls = []
    monkeypatch.setattr(c.s, 'get', lambda *a, **k: calls.append(1) or R(429, ''))
    with pytest.raises(Blocked): c.get('/x', pace=False)
    assert len(calls) == 1

def test_profile_uid_method():
    c, _ = mk([R(200, '<html>"profile_id":"999"</html>')])
    assert c.profile_uid('bob')[0] == '999'

def test_norm_username():
    for x in ['@Form_Leathercraft', 'https://www.instagram.com/form_leathercraft/?igsh=abc', 'instagram.com/form_leathercraft/reels/',
              ' form_leathercraft/ ', 'https://instagram.com/_u/form_leathercraft', 'form_leathercraft?hl=zh-cn']:
        assert I.norm_username(x) == 'form_leathercraft', x

def test_uid_variants():
    for t in ['"props":{"id":"5","x":1}', '"target_id":"5"', '"user_id":"5"', '{"pk":"5","username":"bob"}',
              '{"username":"Bob","full_name":"","id":"5"}', 'meta content="profilePage_5"']:
        assert I.parse_profile_uid(t, 'bob')[0] == '5', t

def test_real_samples():
    import glob, os
    fs = glob.glob('/workspace/ig429/p_*.html')
    if not fs: pytest.skip('no samples')
    for f in fs:
        t = open(f).read()
        if len(t) > 1000: assert I.parse_profile_uid(t, 'form_leathercraft')[0] == '45322071413', f

def test_profile_redirect_login_and_follow():
    c, _ = mk([R(302, '', {'Location': 'https://www.instagram.com/accounts/login/?next=x'})])
    with pytest.raises(Blocked, match='登录页'): c.profile_uid('bob')
    c, _ = mk([R(301, '', {'Location': '/bob/'}), R(200, '"profile_id":"9"')])
    assert c.profile_uid('@Bob')[0] == '9'
    logs = []; c, _ = mk([R(200, '<title>Page</title>')]); c.log = logs.append
    assert c.profile_uid('bob')[0] == '' and '标题「Page」' in logs[-1]

def test_mobile_uid():
    c, _ = mk([R(200, '{"user":{"pk":123,"is_private":false}}')])
    assert c.mobile_uid('bob') == ('123', False)
    h = I.mobile_headers('sessionid=a%3Ab; ds_user_id=1')
    assert h['Authorization'].startswith('Bearer IGT:2:')
