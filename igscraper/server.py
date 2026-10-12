import csv, io, os, socket, threading, webbrowser, time
from flask import Flask, jsonify, request, send_from_directory, Response, send_file
from . import config, db, ai
from .ig import IG, parse_cookie, Blocked
from .task import Task
from .paths import static_dir, data_dir

app = Flask(__name__, static_folder=None)
TASK = Task()
def mask(k): return (k[:4] + '…' + k[-4:]) if k and len(k) > 10 else ('已填写' if k else '')

@app.get('/')
def index(): return send_from_directory(static_dir(), 'index.html')
@app.get('/static/<path:p>')
def st(p): return send_from_directory(static_dir(), p)

@app.get('/api/config')
def get_cfg():
    c = config.load()
    return jsonify({'ai_base': c['ai_base'], 'ai_model': c['ai_model'], 'ai_key_masked': mask(c['ai_key']),
                    'has_cookie': bool(c['cookie']), 'delay_min': c['delay_min'], 'delay_max': c['delay_max'], 'data_dir': data_dir()})
@app.post('/api/config')
def set_cfg():
    d = request.json or {}
    if 'ai_key' in d and not d['ai_key']: d.pop('ai_key')   # empty = keep existing
    config.save(d); return get_cfg()

@app.post('/api/cookie')
def set_cookie():
    raw = (request.json or {}).get('cookie', '')
    try: ck = parse_cookie(raw)
    except Exception as e: return jsonify(ok=False, error=f'Cookie 解析失败: {e}'), 400
    if 'sessionid=' not in ck: return jsonify(ok=False, error='缺少 sessionid，请确认已登录后再导出'), 400
    ig = IG(ck)
    try: ok = ig.check()
    except Blocked as e: return jsonify(ok=False, error=str(e)), 400
    if not ok: return jsonify(ok=False, error='校验失败：接口无返回，Cookie 可能已失效'), 400
    config.save({'cookie': ck}); return jsonify(ok=True, user_id=ig.user_id)
@app.get('/api/cookie/check')
def chk_cookie():
    c = config.load()
    if not c['cookie']: return jsonify(ok=False, error='未填写')
    ig = IG(c['cookie'])
    try: return jsonify(ok=ig.check(), user_id=ig.user_id)
    except Blocked as e: return jsonify(ok=False, error=str(e))

def ai_args(d):
    c = config.load()
    return (d.get('ai_base') or c['ai_base']), (d.get('ai_key') or c['ai_key']), (d.get('ai_model') or c['ai_model'])
@app.post('/api/models')
def models():
    b, k, _ = ai_args(request.json or {})
    try: return jsonify(ok=True, models=ai.list_models(b, k))
    except Exception as e: return jsonify(ok=False, error=f'获取模型失败: {e}')
@app.post('/api/expand')
def expand():
    d = request.json or {}; b, k, m = ai_args(d)
    if not (b and k and m): return jsonify(ok=False, error='请先在「设置」里填写接口地址、Key 并选择模型（也可跳过 AI，直接手动填写）')
    try: return jsonify(ok=True, **ai.expand(b, k, m, d.get('keywords', []), d.get('hashtags', []), d.get('info', [])))
    except Exception as e: return jsonify(ok=False, error=f'AI 裂变失败: {e}')

@app.post('/api/task/start')
def start():
    c = config.load()
    if not c['cookie']: return jsonify(ok=False, error='请先填写 Cookie'), 400
    try: return jsonify(ok=True, run_id=TASK.start(c, request.json or {}))
    except Exception as e: return jsonify(ok=False, error=str(e)), 400
@app.post('/api/task/stop')
def stop(): TASK.stop(); return jsonify(ok=True)
@app.get('/api/task/status')
def status(): return jsonify(TASK.snapshot(int(request.args.get('since', 0))))

@app.get('/api/results')
def results(): return jsonify(db.rows(request.args.get('q', ''), request.args.get('run_id') or None))
@app.post('/api/results/clear')
def clear(): db.clear(); return jsonify(ok=True)
HEAD = [('account','账号'),('url','链接'),('caption','文案'),('plays','播放'),('likes','点赞'),('comment_count','评论数'),
        ('question_count','提问数'),('sample_questions','提问示例'),('publish_date','发布日期'),('source','来源'),('crawled_at','抓取时间')]
@app.get('/api/export')
def export():
    rs = db.rows(request.args.get('q', ''), request.args.get('run_id') or None); fmt = request.args.get('fmt', 'csv')
    name = time.strftime('ig_videos_%Y%m%d_%H%M%S')
    if fmt == 'xlsx':
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.append([h for _, h in HEAD])
        for r in rs: ws.append([r.get(k) for k, _ in HEAD])
        for col, w in zip('ABCDEFGHIJK', [18, 45, 50, 10, 10, 10, 10, 60, 12, 24, 20]): ws.column_dimensions[col].width = w
        bio = io.BytesIO(); wb.save(bio); bio.seek(0)
        return send_file(bio, as_attachment=True, download_name=name + '.xlsx')
    s = io.StringIO(); w = csv.writer(s); w.writerow([h for _, h in HEAD])
    for r in rs: w.writerow([r.get(k) for k, _ in HEAD])
    return Response('\ufeff' + s.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={name}.csv'})

def free_port(pref=8765):
    for p in [pref] + [0]:
        s = socket.socket()
        try: s.bind(('127.0.0.1', p)); port = s.getsockname()[1]; s.close(); return port
        except OSError: s.close()
def run(open_browser=True, port=None):
    db.init(); port = port or free_port()
    url = f'http://127.0.0.1:{port}/'
    print('IG 同行视频采集器已启动:', url, '数据目录:', data_dir(), flush=True)
    if open_browser: threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run('127.0.0.1', port, threaded=True, use_reloader=False)

@app.post('/api/quit')
def quit_app():
    TASK.stop(); threading.Timer(0.5, lambda: os._exit(0)).start(); return jsonify(ok=True)
