import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from igscraper.cfilter import compile_filter
from igscraper.task import cf_hits
V = {'account': 'shop', 'owner_id': '1'}
CS = [{'user': 'a', 'text': 'What is the price?', 'likes': 3}, {'user': 'b', 'text': 'MOQ please', 'likes': 0},
      {'user': 'c', 'text': 'how much for 100 pcs', 'likes': 12}, {'user': 'shop', 'text': 'price in DM'},
      {'user': 'd', 'text': 'beautiful bag', 'likes': 50}, {'user': 'e', 'text': 'cuánto cuesta el precio', 'likes': 1},
      {'user': 'f', 'uid': '1', 'text': 'moq 50 (owner by uid)'}, {'user': 'g', 'text': 'price scam', 'is_reply': 1}]
H = lambda e: [c['user'] for c in cf_hits(compile_filter(e), CS, V, 'tiktok')]
def test_or_quotes_excludes_author():
    assert H('price or moq or "how much"') == ['a', 'b', 'c', 'g']
def test_not_and_chinese():
    assert H('price 不含 scam') == ['a'] and H('(price 或者 moq) and not scam') == ['a', 'b']
def test_likes_reply_user():
    assert H('likes>=10') == ['c', 'd'] and H('点赞>5 and "how much"') == ['c']
    assert H('is_reply:1') == ['g'] and H('user:b') == ['b']
def test_lang():
    assert 'e' in H('lang:es') and 'a' not in H('lang:es')
def test_empty_matches_all_non_author():
    assert len(H('')) == 6
