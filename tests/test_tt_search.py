import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from igscraper.tt import TT

def test_search_passes_search_id_and_stops():
    t = TT.__new__(TT); t.log = lambda *a: None; t.stop = lambda: False
    calls = []
    item = lambda i: {'type': 1, 'item': {'id': str(i)}}
    pages = [{'data': [item(1), item(2)], 'has_more': 1, 'cursor': 12, 'extra': {'logid': 'LID'}},
             {'data': [item(3)], 'has_more': 1, 'cursor': 24, 'extra': {'logid': 'OTHER'}},
             {'data': [item(4)], 'has_more': 0, 'cursor': 36}]
    def api(path, p, ref, fp): calls.append(dict(p)); return pages[len(calls) - 1]
    t.api = api; t.norm = lambda i, s: i['id']
    assert list(t.search('kw', 0)) == ['1', '2', '3', '4']
    assert 'search_id' not in calls[0] and calls[1]['search_id'] == 'LID' and calls[2]['search_id'] == 'LID'
    assert [c['offset'] for c in calls] == ['0', '12', '24']

def test_search_max_pages():
    t = TT.__new__(TT); t.log = lambda *a: None; t.stop = lambda: False; n = [0]
    def api(path, p, ref, fp): n[0] += 1; return {'data': [{'type': 1, 'item': {'id': str(n[0])}}], 'has_more': 1, 'cursor': n[0] * 12, 'extra': {'logid': 'L'}}
    t.api = api; t.norm = lambda i, s: i['id']
    assert len(list(t.search('kw', 3))) == 3
