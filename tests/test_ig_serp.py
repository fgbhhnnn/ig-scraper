import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from igscraper.ig import IG, parse_cookie

def test_serp_medias_and_norm():
    o = {'edges': [{'node': {'__typename': 'XDTTopSerpHeaderUnit'}}, {'node': {'items': [
        {'code': 'ABC', 'pk': '1', 'media_type': 2, 'taken_at': 1749384142, 'comment_count': 5, 'like_count': 9, 'user': {'username': 'u'}, 'caption': {'text': 'hi'}},
        {'code': 'DEF', 'pk': '2', 'media_type': 1, 'taken_at': 1749384142}]}}]}
    ms = IG.serp_medias(o['edges'])
    assert [m['code'] for m in ms] == ['ABC', 'DEF']
    v = IG.norm(ms[0], 'kw:x')
    assert v['url'] == 'https://www.instagram.com/reel/ABC/' and v['content_type'] == 'video' and v['plays_known'] is False and v['comment_count'] == 5
    assert IG.norm(ms[1], 'kw:x')['url'].endswith('/p/DEF/')

def test_parse_cookie_rur_quotes():
    raw = 'sessionid=1%3Aab%3A8%3AX; rur="VLL%2C178%2C179%3A01ff"; ds_user_id=1'
    ck = parse_cookie(raw)
    assert 'rur="VLL%2C178%2C179%3A01ff"' in ck and 'sessionid=1%3Aab%3A8%3AX' in ck
