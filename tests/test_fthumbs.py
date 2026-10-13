import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from igscraper import vai, frames, db

def test_frame_thumbs(tmp_path):
    v = str(tmp_path / 'v.mp4')
    frames._run(['-f', 'lavfi', '-i', 'testsrc=size=720x1280:rate=10:duration=3', '-pix_fmt', 'yuv420p', '-y', v], 60)
    fr = frames.extract_frames(v, str(tmp_path), [0, 0.1, 0.5, 1.0, 2.0])
    th = vai.frame_thumbs(fr, str(tmp_path))
    assert [x['t'] for x in th] == [0, 0.5, 1.0, 2.0]          # 0.1 与 0 太近被去重
    assert all(x['img'].startswith('data:image/jpeg;base64,') and len(x['img']) < 40000 for x in th)

def test_db_column(tmp_path, monkeypatch):
    monkeypatch.setenv('IGS_DATA_DIR', str(tmp_path))
    aid = db.save_analysis({'platform': 'tiktok', 'url': 'u', 'meta': '{}', 'profile': 'p', 'fthumbs': '[{"t":1,"img":"x"}]', 'created_at': 'now'})
    assert db.get_analysis(aid)['fthumbs'] == '[{"t":1,"img":"x"}]'
    aid2 = db.save_analysis({'platform': 'tiktok', 'url': 'u', 'meta': '{}', 'profile': 'p', 'created_at': 'now'})
    assert db.get_analysis(aid2)['fthumbs'] is None

def test_spec_has_highlights():
    assert '## 十、高光镜头' in vai.PROFILE_SPEC
