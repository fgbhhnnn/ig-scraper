import json, os, tempfile
os.environ.setdefault('IGS_DATA_DIR', tempfile.mkdtemp())
from igscraper import social

def test_parse_followers_page():
    j = {'users': [{'pk': 1, 'username': 'a', 'full_name': 'A', 'profile_pic_url': 'u', 'is_verified': True, 'is_private': False},
                   {'pk_id': '2', 'username': 'b'}], 'next_max_id': '25', 'has_more': True}
    us, nxt = social.parse_users(j)
    assert [u['pk'] for u in us] == ['1', '2'] and nxt == '25'
    assert us[0]['profile_url'] == 'https://www.instagram.com/a/' and us[0]['is_verified'] == 1

def test_last_page_and_likers():
    assert social.parse_users({'users': [], 'has_more': False, 'next_max_id': '50'})[1] is None
    us, nxt = social.parse_users({'users': [{'pk': 5, 'username': 'x'}], 'user_count': 10111})
    assert nxt is None and len(us) == 1

def test_dedupe_across_pages():
    seen = set()
    a = social.dedupe([{'pk': '1'}, {'pk': '2'}], seen); b = social.dedupe([{'pk': '2'}, {'pk': '3'}], seen)
    assert [x['pk'] for x in a + b] == ['1', '2', '3']

def test_private_detection():
    assert social.is_private_empty({'users': [], 'has_more': False, 'use_clickable_see_more': False, 'status': 'ok'})
    assert not social.is_private_empty({'users': [{'pk': 1}], 'has_more': True, 'next_max_id': '25'})
    assert social.is_private_empty({'users': []}, target_private=True)

def test_ai_json_parse():
    txt = '好的```json\n[{"username":"@form","type":"品牌商","confidence":"0.9","reason":"logo"},{"username":"b","type":"工厂","confidence":0.5,"reason":"x"},{"username":"c","type":"zzz"}]```'
    r = social.parse_ai_json(txt)
    assert r['form']['type'] == '品牌商' and r['form']['confidence'] == 0.9
    assert r['b']['type'] == '工厂/供应商' and r['c']['type'] == '不确定'

def test_classify_halves_on_error():
    calls = []
    def fake(base, key, model, content, timeout=0):
        n = sum(1 for c in content if c['type'] == 'text') - 1; calls.append(n)
        if n > 5: raise RuntimeError('HTTP 524')
        names = [c['text'].split('username=')[1].split(' ')[0] for c in content[1:] if c['type'] == 'text']
        return json.dumps([{'username': x, 'type': '个人', 'confidence': 0.8, 'reason': 'r'} for x in names])
    us = [{'username': f'u{i}', 'pk': str(i)} for i in range(20)]
    r = social.classify({'ai_base': '', 'ai_key': '', 'ai_model': ''}, us, log=lambda m: None, chat=fake)
    assert len(r) == 20 and calls[0] == 20 and max(calls[1:]) <= 10

def test_shortcode_pk():
    assert social.shortcode_to_pk('DAJLDx8vlqc') == '3461346426913446556'

def test_store_roundtrip():
    social.init()
    social.save_job({'id': 'j1', 'kind': 'followers', 'target': 'a', 'chain': 'a', 'level': 0, 'status': '完成', 'created_at': 'x'})
    social.save_users('j1', [dict(pk='1', username='a1', full_name='', is_verified=0, is_private=0, profile_url='p')], 'followers')
    social.set_types('j1', {'a1': {'type': '品牌商', 'confidence': 0.9, 'reason': 'logo'}})
    assert social.users('j1', '商家')[0]['type'] == '品牌商'
    assert 'a1' in social.export_csv(['j1'])

class _R:
    def __init__(self, code, text, loc=''): self.status_code, self.text, self.headers = code, text, {'Location': loc}
    def json(self): return json.loads(self.text)
class _S:
    def __init__(self, r): self.r, self.headers = r, {}
    def get(self, *a, **k): return self.r
def _req(r):
    from igscraper.ig import IG
    c = IG('sessionid=s; csrftoken=c', 0, 0, lambda *a: None); c._sleep = lambda s: None
    if not hasattr(r, 'cookies'): r.cookies = {}
    c._cs = _S(r); c._cs.cookies = {}
    t = social.SocialTask(); return t.req(c, '/x')
def test_strict_stop_on_throttle():
    import pytest
    from igscraper.ig import Blocked
    for r in [_R(429, ''), _R(401, '{"message":"Please wait a few minutes before you try again.","require_login":true}'),
              _R(400, '{"message":"challenge_required"}'), _R(302, '', 'https://www.instagram.com/accounts/login/')]:
        with pytest.raises(Blocked): _req(r)
    assert _req(_R(200, '{"users":[]}')) == {'users': []}
