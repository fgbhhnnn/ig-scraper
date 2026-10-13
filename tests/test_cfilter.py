import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from igscraper.cfilter import compile_filter, parse, FilterError
C = lambda text, **k: dict(dict(text=text, lang='en', commenter='bob', likes=0, is_reply=0, platform='tiktok', region=''), **k)
def m(expr, text, **k): return compile_filter(expr)(C(text, **k))
def test_basic():
    assert m('price and moq', 'Price? MOQ?') and not m('price and moq', 'price only')
    assert m('price or moq', 'moq pls') and m('', 'anything')
def test_symbols_and_chinese():
    assert m('price&&moq', 'price moq') and m('price&moq', 'price moq') and m('price & moq', 'price moq')
    assert m('price || moq', 'moq') and m('!scam', 'good') and not m('!scam', 'SCAM!!')
    assert m('价格并且起订量', '价格多少 起订量多少') and m('价格或者多少钱', '多少钱') and m('price 不含 scam', 'price?')
    assert not m('price 不含 scam', 'price scam')
def test_parens_quotes_not():
    e = '(price or "how much") and not scam'
    assert m(e, 'How much is it') and not m(e, 'how much scam') and not m(e, 'nice')
    assert m('-scam price', 'price') and m('"how much"', 'HOW MUCH?')
def test_implicit_and_and_wordmatch():
    assert m('price moq', 'moq & price') and not m('price moq', 'price')
    assert m('price', 'prices?') and not m('rice', 'price')   # word-start
    assert m('brand', 'Brand new') and m('"and"', 'this and that')   # quote to search an operator word
    assert m('candle', 'candle') and not m('price', 'priceless') is False
def test_fields():
    assert m('lang:es and precio', 'precio?', lang='es') and not m('lang:es', 'x', lang='en')
    assert m('likes>5', 'x', likes=6) and not m('likes>5', 'x', likes=5) and m('likes>=5', 'x', likes=5)
    assert m('is_reply:1', 'x', is_reply=1) and m('user:bo', 'x') and m('platform:tik', 'x') and m('lang!=en', 'x', lang='es')
def test_errors():
    for e in ['(price', 'price)', 'price and', 'and price', 'likes>abc', 'foo:bar', '()', 'price or or moq', 'and']:
        with pytest.raises(FilterError): parse(e)
