import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from igscraper.vai import clean_err, _too_many, _no_vision, AIError
CF = '<!DOCTYPE html><html><head><title>lllltt.com | 524: A timeout occurred</title></head><body>' + 'x' * 5000 + '</body></html>'
def test_clean_cloudflare():
    m = clean_err(524, CF)
    assert m.startswith('HTTP 524') and '超时' in m and '<' not in m and len(m) < 200
def test_clean_json():
    assert clean_err(400, '{"error":{"message":"Too many images"}}') == 'HTTP 400: Too many images'
def test_retryable():
    for st in (524, 504, 502):
        assert _too_many(AIError(clean_err(st, CF), st, CF))
    assert _too_many(AIError('网络错误/超时: read timed out', 524))
    assert _too_many(AIError('HTTP 400: Too many images', 400, 'too many images'))
    assert not _too_many(AIError('HTTP 401: bad key', 401, 'unauthorized'))
    assert _no_vision(AIError('HTTP 400: model does not support image input', 400, 'does not support image input'))
