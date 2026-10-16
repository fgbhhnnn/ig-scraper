from igscraper import ig

def test_jazoest_matches_page():
    # 页面 HTML 里的 jazoest=22275 对应 lsd=AdSealw8_WRigMh16T8BnUHeA_8（2026-10 实测）
    assert ig.jazoest('AdSealw8_WRigMh16T8BnUHeA_8') == '22275'
    assert ig.jazoest('') == '20'

def test_scan_js():
    js = ('__d("PolarisPostRootQuery_instagramRelayOperation",[],(function(t,n,r,o,a,i){a.exports="123456789012"}),null);'
          '__d("OtherQuery_instagramRelayOperation",[],(function(t,n,r,o,a,i){a.exports="999"}),null);'
          '__d("BDHeaderConfig",[],(function(t,n,r,o,a,i){"use strict";var e="359341";i.ASBD_ID=e}),66);')
    assert ig.scan_js(js, {'PolarisPostRootQuery'}) == {'PolarisPostRootQuery': '123456789012', '_asbd': '359341'}

def test_doc_override():
    ig.DISCOVERED['PolarisPostRootQuery'] = '42'
    try: assert ig.IG.doc(ig.POST_DOC) == ('PolarisPostRootQuery', '42')
    finally: ig.DISCOVERED.pop('PolarisPostRootQuery')

def test_doc_stale():
    assert ig.doc_stale(None, 403)
    assert not ig.doc_stale({'data': {'x': 1}}, 200)
    assert ig.doc_stale({'errors': [{'message': 'PersistedQueryNotFound'}]}, 200)
    assert not ig.doc_stale({'errors': [{'message': 'Unauthorized logged out query.'}]}, 200)

def test_page_app_id():
    assert ig.page_app_id('..."X-IG-App-ID":"936619743392459"...') == '936619743392459'
