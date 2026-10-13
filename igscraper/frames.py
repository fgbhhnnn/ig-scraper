"""视频抽帧 / 音频提取（ffmpeg）。抽帧策略：开头 dense_secs 秒按 dense_fps 密集截图，之后按 fps 截图，再补充转场(场景切换)帧。"""
import os, re, shutil, subprocess, sys
NOWIN = 0x08000000 if os.name == 'nt' else 0   # CREATE_NO_WINDOW: 打包后的窗口程序里不弹黑框

def frame_schedule(duration, fps=1.0, dense_secs=3.0, dense_fps=4.0, scene_times=(), min_gap=0.3):
    """返回排好序的截图时间点（秒）。scene_times 中离已有时间点 < min_gap 的会被丢掉。"""
    d = float(duration or 0)
    if d <= 0: return [0.0]
    fps = max(0.1, float(fps)); dense_fps = max(fps, float(dense_fps))
    end = d - 0.05; ts = []; t = 0.0; ds = min(float(dense_secs), d)
    while t < ds - 1e-9 and t <= end: ts.append(round(t, 3)); t += 1.0 / dense_fps
    t = ds
    while t <= end + 1e-9: ts.append(round(t, 3)); t += 1.0 / fps
    for s in sorted(scene_times):
        if 0 <= s <= end and all(abs(s - x) >= min_gap for x in ts): ts.append(round(float(s), 3))
    return sorted(set(ts))

def ffmpeg_path():
    if getattr(sys, 'frozen', False):
        import glob
        for p in sorted(glob.glob(os.path.join(sys._MEIPASS, 'ffmpeg', 'ffmpeg*'))): return p
    p = shutil.which('ffmpeg')
    if p: return p
    try:
        import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception: pass
    raise RuntimeError('找不到 ffmpeg（打包版已内置；源码运行请安装 ffmpeg 或 pip install imageio-ffmpeg）')

def _run(args, timeout=600):
    return subprocess.run([ffmpeg_path(), '-hide_banner'] + args, capture_output=True, timeout=timeout, creationflags=NOWIN)

def probe(video):
    """-> (duration 秒, has_audio)"""
    r = _run(['-i', video], 60); e = r.stderr.decode('utf-8', 'ignore')
    m = re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)', e)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    return dur, bool(re.search(r'Stream #.*Audio:', e))

def scene_times(video, thresh=0.35):
    r = _run(['-i', video, '-an', '-vf', f"select='gt(scene,{thresh})',showinfo", '-f', 'null', '-'], 900)
    return [float(x) for x in re.findall(r'pts_time:([\d.]+)', r.stderr.decode('utf-8', 'ignore'))]

def extract_frames(video, outdir, times, width=512, quality=5):
    """每个时间点截一张 JPEG（宽 width，高等比），返回 [(t, path)]。"""
    out = []
    for i, t in enumerate(times):
        p = os.path.join(outdir, f'f{i:04d}_{t:07.2f}.jpg')
        _run(['-ss', f'{t:.3f}', '-i', video, '-frames:v', '1', '-vf', f'scale={width}:-2', '-q:v', str(quality), '-y', p], 120)
        if os.path.exists(p) and os.path.getsize(p) > 0: out.append((t, p))
    return out

def extract_audio(video, out_path):
    r = _run(['-i', video, '-vn', '-ac', '1', '-ar', '16000', '-b:a', '48k', '-y', out_path], 600)
    return out_path if os.path.exists(out_path) and os.path.getsize(out_path) > 1000 else None
