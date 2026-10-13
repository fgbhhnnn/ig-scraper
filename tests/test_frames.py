import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from igscraper.frames import frame_schedule
def test_dense_then_1fps():
    ts = frame_schedule(7.0, fps=1)
    assert ts[:12] == [0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 2.75]
    assert ts[12:] == [3, 4, 5, 6]
def test_2fps_tail():
    ts = frame_schedule(5.0, fps=2)
    assert ts[12:] == [3, 3.5, 4, 4.5]
def test_short_video():
    assert frame_schedule(1.0, fps=1) == [0, 0.25, 0.5, 0.75]
    assert frame_schedule(0) == [0.0]
def test_scene_merge():
    ts = frame_schedule(10, fps=1, scene_times=[3.1, 7.5, 9.99, 0.1])
    assert 7.5 in ts and 3.1 not in ts and 0.1 not in ts and 9.99 not in ts
    assert ts == sorted(ts) and len(ts) == len(set(ts))
def test_long_video_count():
    assert len(frame_schedule(60, fps=1)) == 12 + 57
    assert len(frame_schedule(60, fps=2)) == 12 + 114
