import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from igscraper.fb import page_owner, video_url, page_stats

REEL = ('"owner":{"__typename":"User","id":"615"},"x":1,"actors":[{"__typename":"User","id":"615","__isActor":"User","name":"Jason bagfactory","url":"u"}],'
        '"videoDeliveryLegacyFields":{"progressive_urls":[{"progressive_url":"https:\\/\\/other\\/sd.mp4","metadata":{"quality":"SD"}}],"id":"999"},'
        '"progressive_urls":[{"progressive_url":"https:\\/\\/cdn\\/sd.mp4","failure_reason":null,"metadata":{"quality":"SD"}},{"progressive_url":"https:\\/\\/cdn\\/hd.mp4","metadata":{"quality":"HD"}}],'
        '"hls_playlist_urls":[],"id":"1336"},"unified_reactors":{"count":2559},"total_comment_count":272,"creation_time":1784031276,"playable_duration_in_ms":28246')
VIDEO = ('"owning_profile":{"__typename":"User","id":"100","short_name":"S"},"stuff":{"id":"100","name":"Sky","is_verified":false},'
         '"browser_native_sd_url":"https:\\/\\/old\\/sd.mp4","play_count":45858,"reaction_count":{"count":1482},"comments":{"total_count":339},"share_count":{"count":107},"publish_time":1663944836')

def test_owner():
    assert page_owner(REEL) == ('Jason bagfactory', '615')
    assert page_owner(VIDEO) == ('Sky', '100')
    assert page_owner('{}') == ('', '')

def test_video_url_prefers_own_hd():
    assert video_url(REEL, '1336') == 'https://cdn/hd.mp4'
    assert video_url(REEL, '') == 'https://other/sd.mp4'
    assert video_url(VIDEO) == 'https://old/sd.mp4'
    assert video_url('{}') is None

def test_stats():
    s = page_stats(REEL)
    assert s['likes'] == 2559 and s['comments'] == 272 and s['plays'] is None and abs(s['duration'] - 28.246) < 1e-6 and s['date'].startswith('2026-07')
    s = page_stats(VIDEO)
    assert (s['plays'], s['likes'], s['comments'], s['shares']) == (45858, 1482, 339, 107) and s['date'] == '2022-09-23'

def test_stats_nearest_to_video():
    other = '"id":"777",' + '"unified_reactors":{"count":78079},"total_comment_count":6500,' + 'x' * 3000
    s = page_stats(other + REEL, '1336')
    assert s['likes'] == 2559 and s['comments'] == 272
