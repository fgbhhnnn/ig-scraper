import csv, io, os, re, socket, threading, webbrowser, time
from flask import Flask, jsonify, request, send_from_directory, Response, send_file
from . import config, db, ai
from .ig import IG, parse_cookie, Blocked
from .task import Task
from .paths import static_dir, data_dir

app = Flask(__name__, static_folder=None)
TASK = Task()
from .ctask import CommentTask
CTASK = CommentTask()
def mask(k): return (k[:4] + '…' + k[-4:]) if k and len(k) > 10 else ('已填写' if k else '')

@app.get('/')
def index(): return send_from_directory(static_dir(), 'index.html')
@app.get('/static/<path:p>')
def st(p): return send_from_directory(static_dir(), p)

@app.get('/api/config')
def get_cfg():
    c = config.load()
    return jsonify({'ai_base': c['ai_base'], 'ai_model': c['ai_model'], 'ai_key_masked': mask(c['ai_key']),
                    'has_cookie': bool(c['cookie']), 'has_fb_cookie': bool(c['fb_cookie']), 'has_tt_cookie': bool(c['tt_cookie']),
                    'tt_ms_token_set': bool(c['tt_ms_token']), 'tt_device_id': c['tt_device_id'], 'tt_user_agent': c['tt_user_agent'],
                    'tt_delay_min': c['tt_delay_min'], 'tt_delay_max': c['tt_delay_max'], 'port': c['port'], 'running_port': PORT[0],
                    'fb_delay_min': c['fb_delay_min'], 'fb_delay_max': c['fb_delay_max'], 'delay_min': c['delay_min'], 'delay_max': c['delay_max'], 'data_dir': data_dir(),
                    **{k: c[k] for k in ('ai_fps', 'ai_max_images', 'ai_stt_model', 'ai_vision', 'ai_comment_pages', 'ai_comments_send', 'el_model', 'el_lang')}, 'ai_stt_provider': vai.stt_provider(c), 'el_key_masked': mask(c['el_key'])})
@app.post('/api/config')
def set_cfg():
    d = request.json or {}
    for kk in ('ai_key', 'el_key'):
        if kk in d and not d[kk]: d.pop(kk)   # empty = keep existing
    config.save(d); return get_cfg()

def _check(plat, ck, extra=None):
    if plat == 'tiktok':
        from .tt import TT, parse_session
        c = config.load(); e = extra or {}
        sess = parse_session(ck, e.get('tt_ms_token', c['tt_ms_token']), e.get('tt_device_id', c['tt_device_id']), e.get('tt_user_agent', c['tt_user_agent']))
        uid, name = TT(sess).me()
        return f'{uid} {name}'.strip()
    if plat == 'facebook':
        from .fb import FB
        return FB(ck).login()
    ig = IG(ck)
    return ig.check()
    return ig.user_id
@app.post('/api/cookie')
def set_cookie():
    d = request.json or {}; plat = d.get('platform', 'instagram')
    try: ck = parse_cookie(d.get('cookie', ''))
    except Exception as e: return jsonify(ok=False, error=f'Cookie 解析失败: {e}'), 400
    KEY = {'facebook': 'fb_cookie', 'tiktok': 'tt_cookie'}.get(plat, 'cookie')
    extra = {k: (d.get(k) or '').strip() for k in ('tt_ms_token', 'tt_device_id', 'tt_user_agent') if k in d}
    if plat == 'tiktok':
        from .tt import parse_session
        if not ck and config.load()['tt_cookie']: ck = config.load()['tt_cookie']   # only updating extra fields
        sess = parse_session(ck, extra.get('tt_ms_token'), extra.get('tt_device_id'), extra.get('tt_user_agent'))
        if not sess['logged_in']: return jsonify(ok=False, error='缺少 sessionid（HttpOnly）。请用 Cookie-Editor 导出 JSON，普通 document.cookie 拿不到'), 400
        if 'tt_device_id' in extra: extra['tt_device_id'] = sess['device_id']
        if d.get('cookie') and ck != config.load()['tt_cookie'] and not extra.get('tt_ms_token'): extra['tt_ms_token'] = ''   # new login: drop old saved msToken, use the cookie's
    else:
        need = 'c_user=' if plat == 'facebook' else 'sessionid='
        if need not in ck or (plat == 'facebook' and 'xs=' not in ck):
            return jsonify(ok=False, error=f'缺少 {"c_user / xs" if plat == "facebook" else "sessionid"}，请确认已登录后再导出'), 400
    try: uid = _check(plat, ck, extra)
    except Blocked as e: return jsonify(ok=False, error=str(e)), 400
    except Exception as e: return jsonify(ok=False, error=f'校验出错: {e}'), 400
    config.save(dict({KEY: ck}, **extra)); return jsonify(ok=True, user_id=uid)
@app.get('/api/cookie/check')
def chk_cookie():
    plat = request.args.get('platform', 'instagram')
    ck = config.load()[{'facebook': 'fb_cookie', 'tiktok': 'tt_cookie'}.get(plat, 'cookie')]
    if not ck: return jsonify(ok=False, error='未填写')
    try: return jsonify(ok=True, user_id=_check(plat, ck))
    except Exception as e: return jsonify(ok=False, error=str(e))

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
    c = config.load(); d = request.json or {}
    if not c[{'facebook': 'fb_cookie', 'tiktok': 'tt_cookie'}.get(d.get('platform'), 'cookie')]:
        return jsonify(ok=False, error='请先在「Cookie」页面填写该平台的 Cookie'), 400
    if _running(): return jsonify(ok=False, error='已有任务在运行，请先停止'), 400
    try: return jsonify(ok=True, run_id=TASK.start(c, request.json or {}))
    except Exception as e: return jsonify(ok=False, error=str(e)), 400
@app.post('/api/task/stop')
def stop(): TASK.stop(); return jsonify(ok=True)
@app.get('/api/task/status')
def status(): return jsonify(TASK.snapshot(int(request.args.get('since', 0))))

@app.get('/api/results')
def results(): return jsonify(db.rows(request.args.get('q', ''), request.args.get('run_id') or None, request.args.get('platform') or None, request.args.get('content_type') or None))
@app.post('/api/results/clear')
def clear(): db.clear(); return jsonify(ok=True)
PLAT = {'instagram': 'Instagram', 'facebook': 'Facebook', 'tiktok': 'TikTok'}; CT = {'video': '视频', 'post': '帖子'}
HEAD = [('platform','平台'),('content_type','类型'),('account','账号'),('url','链接'),('caption','文案'),('plays','播放/观看'),('likes','点赞/心情'),('comment_count','评论数'),('shares','分享'),
        ('question_count','提问数'),('sample_questions','提问示例'),('cf_count','评论筛选命中数'),('cf_samples','命中评论示例'),('publish_date','发布日期'),('source','来源'),('crawled_at','抓取时间')]
def fmtv(r, k):
    v = r.get(k)
    return PLAT.get(v, v) if k == 'platform' else CT.get(v, v) if k == 'content_type' else v
@app.get('/api/export')
def export():
    rs = db.rows(request.args.get('q', ''), request.args.get('run_id') or None, request.args.get('platform') or None, request.args.get('content_type') or None); fmt = request.args.get('fmt', 'csv')
    name = time.strftime('social_%Y%m%d_%H%M%S')
    if fmt == 'xlsx':
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.append([h for _, h in HEAD])
        for r in rs: ws.append([fmtv(r, k) for k, _ in HEAD])
        for col, w in zip('ABCDEFGHIJKLMNOP', [10, 6, 18, 45, 50, 10, 10, 10, 8, 10, 60, 10, 60, 12, 24, 20]): ws.column_dimensions[col].width = w
        bio = io.BytesIO(); wb.save(bio); bio.seek(0)
        return send_file(bio, as_attachment=True, download_name=name + '.xlsx')
    s = io.StringIO(); w = csv.writer(s); w.writerow([h for _, h in HEAD])
    for r in rs: w.writerow([fmtv(r, k) for k, _ in HEAD])
    return Response('\ufeff' + s.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={name}.csv'})

APP_ID = 'social-scraper'
PORT = [8765]
@app.get('/api/ping')
def ping():
    from . import __version__
    return jsonify(app=APP_ID, port=PORT[0], version=__version__)

def _alert(msg):
    print(msg, flush=True)
    if os.name == 'nt':
        try:
            import ctypes; ctypes.windll.user32.MessageBoxW(0, msg, '社媒同行采集器', 0x10)
        except Exception: pass

def _port_busy(port):
    s = socket.socket()
    try: s.bind(('127.0.0.1', port)); return False
    except OSError: return True
    finally: s.close()

def _is_ours(port):
    import requests as _r
    try: return _r.get(f'http://127.0.0.1:{port}/api/ping', timeout=3).json().get('app') == APP_ID
    except Exception: return False

def run(open_browser=True, port=None):
    """Fixed port (config.json 'port', default 8765). Reuse a running instance; never fall back to random."""
    cfg = config.load()
    if not os.path.exists(config.path()): config.save({'port': cfg.get('port', 8765)})   # so users can find/edit it
    try: port = int(port or cfg.get('port') or 8765)
    except Exception: port = 8765
    PORT[0] = port
    url = f'http://127.0.0.1:{port}/'
    if _port_busy(port):
        if _is_ours(port):
            print('程序已在运行，直接打开:', url, flush=True)
            if open_browser: webbrowser.open(url)
            return 0
        _alert(f'端口 {port} 已被其他程序占用，无法启动。\n\n解决方法：\n1. 关闭占用 {port} 端口的程序后重新打开；或\n'
               f'2. 用记事本打开 {os.path.join(data_dir(), "config.json")}，把 "port" 改成其他端口（如 8766），保存后重新打开。')
        return 2
    db.init()
    try:
        from . import updater; updater.startup_cleanup()
    except Exception: pass
    print('社媒同行采集器已启动:', url, '数据目录:', data_dir(), flush=True)
    if open_browser: threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run('127.0.0.1', port, threaded=True, use_reloader=False)
    return 0

@app.post('/api/tt/diag')
def tt_diag():
    from .tt import TT, parse_session
    cfg = config.load()
    if not cfg.get('tt_cookie'): return jsonify(ok=False, lines=['❌ 还没有保存 TikTok Cookie'])
    lines = []
    c = TT(parse_session(cfg['tt_cookie'], cfg.get('tt_ms_token'), cfg.get('tt_device_id'), cfg.get('tt_user_agent')), 0.5, 1, lines.append)
    try: res = c.diag()
    except Exception as e: res = [f'❌ {e}']
    return jsonify(ok=True, lines=res + lines)

@app.post('/api/ig/diag')
def ig_diag():
    cfg = config.load()
    if not cfg.get('cookie'): return jsonify(ok=False, lines=['❌ 还没有保存 Instagram Cookie'])
    lines = []
    try: res = IG(cfg['cookie'], 0.3, 0.6, lines.append).diag()
    except Exception as e: res = [f'❌ {e}']
    return jsonify(ok=True, lines=res)

@app.get('/api/tt/signer')
def tt_signer():
    from . import ttsign
    return jsonify(ttsign.status())
@app.post('/api/tt/signer')
def tt_signer_install():
    from . import ttsign
    try:
        f = request.files.get('file')
        return jsonify(ttsign.install(f.read() if f else None))
    except Exception as e: return jsonify(ok=False, msg=f'安装失败: {e}')

def _running():
    return (TASK.thread and TASK.thread.is_alive()) or (CTASK.thread and CTASK.thread.is_alive())
@app.post('/api/ctask/start')
def cstart():
    d = request.json or {}
    if _running(): return jsonify(ok=False, error='已有任务在运行，请先停止'), 400
    if d.get('use_filtered'):
        d['items'] = db.rows(d.get('q', ''), None, d.get('platform') or None, d.get('content_type') or None)
    elif d.get('keys'): d['items'] = db.get_videos(d['keys'])
    d['max_videos'] = len(d.get('items') or []) + len(d.get('urls') or [])
    try: return jsonify(ok=True, run_id=CTASK.start(config.load(), d), count=d['max_videos'])
    except Exception as e: return jsonify(ok=False, error=str(e)), 400
@app.post('/api/ctask/stop')
def cstop(): CTASK.stop(); return jsonify(ok=True)
@app.get('/api/ctask/status')
def cstatus(): return jsonify(CTASK.snapshot(int(request.args.get('since', 0))))

def _filtered_comments(a):
    from .cfilter import compile_filter, FilterError
    rows = db.comment_rows(a.get('platform') or None, a.get('run_id') or None, a.get('post_url') or None)
    try: f = compile_filter(a.get('expr', ''))
    except FilterError as e: return None, str(e)
    exw = [w.strip().lower() for w in re.split(r'[,，\n]', a.get('ex_words', '')) if w.strip()]
    exu = [w.strip().lower() for w in re.split(r'[,，\n]', a.get('ex_users', '')) if w.strip()]
    hide_author, hide_spam = a.get('hide_author', '1') == '1', a.get('hide_spam', '0') == '1'
    only_m = a.get('only_matched', '0') == '1'
    out = []
    for r in rows:
        tl = (r['text'] or '').lower()
        if hide_author and r['is_author']: continue
        if hide_spam and r['is_spam']: continue
        if only_m and not r['matched']: continue
        if exw and any(w in tl for w in exw): continue
        if exu and (r['commenter'] or '').lower() in exu: continue
        if f(r): out.append(r)
    return out, None
@app.get('/api/comments')
def comments():
    rows, err = _filtered_comments(request.args)
    if err: return jsonify(ok=False, error=err)
    langs = {}
    for r in rows: langs[(r['lang'], r['lang_name'])] = langs.get((r['lang'], r['lang_name']), 0) + 1
    lim = int(request.args.get('limit', 2000))
    return jsonify(ok=True, total=len(rows), rows=rows[:lim], langs=sorted([{'lang': k[0], 'name': k[1], 'n': v} for k, v in langs.items()], key=lambda x: -x['n']))
CHEAD = [('platform','平台'),('post_url','帖子链接'),('account','账号'),('commenter','评论者'),('text','评论内容'),('lang','语言代码'),
         ('lang_name','语言'),('region','可能地区(按语言推断)'),('likes','点赞'),('ctime','评论时间'),('is_reply','是否回复'),
         ('matched','询盘匹配'),('is_author','作者本人'),('crawled_at','抓取时间')]
@app.get('/api/comments/export')
def cexport():
    a = request.args
    rows, err = _filtered_comments(a) if a.get('all') != '1' else (db.comment_rows(), None)
    if err: return Response(err, status=400)
    name = time.strftime('comments_%Y%m%d_%H%M%S')
    val = lambda r, k: PLAT.get(r[k], r[k]) if k == 'platform' else ('是' if r[k] else '否') if k in ('is_reply', 'matched', 'is_author') else r[k]
    if a.get('fmt') == 'xlsx':
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.append([h for _, h in CHEAD])
        for r in rows: ws.append([val(r, k) for k, _ in CHEAD])
        for col, w in zip('ABCDEFGHIJKLMN', [10, 45, 18, 18, 70, 8, 10, 24, 8, 16, 8, 8, 8, 18]): ws.column_dimensions[col].width = w
        bio = io.BytesIO(); wb.save(bio); bio.seek(0)
        return send_file(bio, as_attachment=True, download_name=name + '.xlsx')
    s = io.StringIO(); w = csv.writer(s); w.writerow([h for _, h in CHEAD])
    for r in rows: w.writerow([val(r, k) for k, _ in CHEAD])
    return Response('\ufeff' + s.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={name}.csv'})
@app.post('/api/comments/clear')
def cclear(): db.clear_comments(); return jsonify(ok=True)

from . import vai
ATASK = vai.AnalyzeTask()
@app.post('/api/ai/vision_test')
def vision_test():
    b, k, m = ai_args(request.json or {})
    if not (b and k and m): return jsonify(ok=False, msg='请先填写接口地址、Key 并选择模型')
    ok, msg = vai.vision_test(b, k, m)
    return jsonify(ok=ok, msg=msg)
@app.post('/api/ai/stt_test')
def stt_test():
    d = request.json or {}; c = config.load()
    ok, msg = vai.el_test((d.get('el_key') or '').strip() or c['el_key'], (d.get('el_model') or '').strip() or c['el_model'] or vai.EL_MODEL)
    return jsonify(ok=ok, msg=msg)
@app.get('/api/ffmpeg')
def ffmpeg_info():
    from . import frames
    try:
        p = frames.ffmpeg_path(); v = frames._run(['-version'], 30).stdout.decode('utf-8', 'ignore').split('\n')[0]
        return jsonify(ok=True, path=p, version=v)
    except Exception as e: return jsonify(ok=False, error=str(e))
@app.post('/api/analyze/start')
def analyze_start():
    d = request.json or {}
    if ATASK.thread and ATASK.thread.is_alive(): return jsonify(ok=False, error='已有分析在进行，请等它完成或先停止'), 400
    ATASK.state['result_id'] = None
    try: return jsonify(ok=True, run_id=ATASK.start(config.load(), dict(d, max_videos=6)))
    except Exception as e: return jsonify(ok=False, error=str(e)), 400
@app.post('/api/analyze/stop')
def analyze_stop(): ATASK.stop(); return jsonify(ok=True)
@app.get('/api/analyze/status')
def analyze_status(): return jsonify(ATASK.snapshot(int(request.args.get('since', 0))))
@app.get('/api/analyses')
def analyses(): return jsonify(db.list_analyses())
@app.get('/api/analyses/<int:aid>')
def analysis(aid): return jsonify(db.get_analysis(aid) or {})
@app.post('/api/analyses/<int:aid>/delete')
def analysis_del(aid): db.delete_analysis(aid); return jsonify(ok=True)
@app.post('/api/analyses/<int:aid>/replicate')
def analysis_rep(aid):
    d = request.json or {}; prod = d.get('product') or {}
    if isinstance(prod, dict): config.save({'ai_product': prod})
    try: vai.replicate_start(aid, prod); return jsonify(ok=True)
    except Exception as e: return jsonify(ok=False, error=f'生成失败: {e}')
@app.get('/api/analyses/<int:aid>/replicate/status')
def analysis_rep_status(aid):
    st = vai.REP.get(aid)
    if not st: return jsonify(running=False, text='', error=None, elapsed=0)
    return jsonify(running=st['running'], text=st['text'], error=st['error'], elapsed=round(st.get('elapsed') or (time.time() - st['started']), 1))
@app.get('/api/product')
def get_product(): return jsonify(config.load().get('ai_product') or {})
@app.get('/api/analyses/<int:aid>/md')
def analysis_md(aid):
    a = db.get_analysis(aid)
    if not a: return Response('not found', status=404)
    md = vai.to_markdown(a)
    if request.args.get('raw'): return Response(md, mimetype='text/plain; charset=utf-8')
    return Response(md.encode('utf-8'), mimetype='text/markdown; charset=utf-8', headers={'Content-Disposition': f'attachment; filename=ai_analysis_{aid}.md'})

@app.get('/api/cfilter/check')
def cfilter_check():
    from .cfilter import compile_filter, FilterError
    try: compile_filter(request.args.get('expr', '')); return jsonify(ok=True)
    except FilterError as e: return jsonify(ok=False, error=str(e))

@app.post('/api/quit')
def quit_app():
    TASK.stop(); threading.Timer(0.5, lambda: os._exit(0)).start(); return jsonify(ok=True)

from . import updater, __version__
@app.get('/api/update/check')
def upd_check():
    try:
        d = updater.check(); d['skipped'] = d['newer'] and config.load().get('skip_version') == d['latest']
        d['can_apply'] = bool(updater.exe_path()); return jsonify(ok=True, **d)
    except Exception as e: return jsonify(ok=False, current=__version__, error=f'检查更新失败：{e}')
@app.post('/api/update/skip')
def upd_skip():
    config.save({'skip_version': (request.json or {}).get('version', '')}); return jsonify(ok=True)
@app.post('/api/update/download')
def upd_download():
    try: updater.start_download((request.json or {}).get('url', '')); return jsonify(ok=True)
    except Exception as e: return jsonify(ok=False, error=str(e))
@app.get('/api/update/status')
def upd_status(): return jsonify(updater.ST)
@app.post('/api/update/apply')
def upd_apply():
    try: TASK.stop(); updater.apply(); return jsonify(ok=True)
    except Exception as e: return jsonify(ok=False, error=str(e))

from . import social
STASK = social.SocialTask()
try: social.mark_interrupted()
except Exception: pass
@app.post('/api/social/start')
def social_start():
    c = config.load(); d = request.json or {}
    if not c['cookie']: return jsonify(ok=False, error='请先在「Cookie」页面填写 Instagram Cookie'), 400
    js = []
    if d.get('kind') == 'likers':
        v = (db.get_videos([d['key']]) or [{}])[0] if d.get('key') else {}
        code = v.get('shortcode') or d.get('shortcode') or ''
        js.append({'kind': 'likers', 'media_pk': v.get('media_id') or d.get('media_pk') or '', 'shortcode': code,
                   'url': v.get('url') or d.get('url') or '', 'target': (v.get('account') or '') + ' 的视频 ' + code})
    else:
        which = d.get('which', 'followers'); kinds = ['followers', 'following'] if which == 'both' else [which]
        cnt = 0 if d.get('all') else max(1, int(d.get('count') or 100))
        for t in d.get('targets') or []:
            if isinstance(t, str): t = {'target': t}
            un = (t.get('target') or '').strip().lstrip('@').split('?')[0].rstrip('/').split('/')[-1]
            if not un: continue
            for k in kinds:
                chain = (t.get('chain') + ' → ' + un) if t.get('chain') else un
                js.append({'kind': k, 'target': un, 'target_pk': t.get('pk') or '', 'count': cnt, 'chain': chain,
                           'level': int(t.get('level') or 0), 'parent': t.get('parent') or ''})
    if not js: return jsonify(ok=False, error='请填写至少一个账号'), 400
    return jsonify(ok=True, ids=STASK.add(c, js))
@app.post('/api/social/stop')
def social_stop(): STASK.stop(); return jsonify(ok=True)
@app.get('/api/social/status')
def social_status(): return jsonify(STASK.snapshot(int(request.args.get('since', 0))))
@app.get('/api/social/jobs')
def social_jobs(): return jsonify(social.jobs())
@app.get('/api/social/users')
def social_users(): return jsonify(social.users(request.args.get('job_id', ''), request.args.get('type', '')))
@app.post('/api/social/delete')
def social_del(): social.delete_job((request.json or {}).get('job_id', '')); return jsonify(ok=True)
@app.get('/api/social/export')
def social_export():
    ids = [x for x in request.args.get('job_ids', '').split(',') if x]
    return Response(social.export_csv(ids), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={time.strftime("ig_accounts_%Y%m%d_%H%M%S")}.csv'})
