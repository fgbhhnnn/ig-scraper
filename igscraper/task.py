import threading, time, datetime, re, uuid
from . import db
from .ig import IG, Blocked
from .matcher import Matcher

class Task:
    def __init__(self):
        self.lock = threading.Lock(); self.thread = None; self._stop = False
        self.state = {'running': False, 'stage': '空闲', 'scanned': 0, 'candidates': 0, 'matched': 0, 'skipped': 0,
                      'target': 0, 'current': '', 'logs': [], 'run_id': None, 'error': None, 'started': None, 'ended': None}
    def log(self, msg):
        line = time.strftime('%H:%M:%S ') + str(msg)
        with self.lock:
            self.state['logs'].append(line); self.state['logs'] = self.state['logs'][-500:]
    def set(self, **kw):
        with self.lock: self.state.update(kw)
    def snapshot(self, since=0):
        with self.lock:
            s = dict(self.state); s['log_total'] = len(s['logs']); s['logs'] = s['logs'][since:] if since <= len(s['logs']) else s['logs']
            return s
    def stop(self): self._stop = True; self.log('收到停止指令…')
    def start(self, cfg, params):
        if self.thread and self.thread.is_alive(): raise RuntimeError('已有任务在运行')
        self._stop = False
        rid = time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:4]
        self.state.update({'running': True, 'stage': '准备', 'scanned': 0, 'candidates': 0, 'matched': 0, 'skipped': 0,
                           'target': int(params.get('max_videos') or 20), 'current': '', 'logs': [], 'run_id': rid,
                           'error': None, 'started': time.time(), 'ended': None})
        self.thread = threading.Thread(target=self._run, args=(cfg, params, rid), daemon=True); self.thread.start()
        return rid

    def _run(self, cfg, P, rid):
        try: self._crawl(cfg, P, rid)
        except Blocked as e: self.log('⛔ ' + str(e)); self.set(error=str(e))
        except Exception as e: self.log('❌ 出错: %r' % e); self.set(error=repr(e))
        finally:
            self.set(running=False, ended=time.time(), stage='已停止' if self._stop else ('出错' if self.state['error'] else '完成'), current='')

    def _crawl(self, cfg, P, rid):
        plat = P.get('platform', 'instagram')
        ctype = P.get('content_type', 'video')        # video | post | both
        want = lambda v: ctype == 'both' or v['content_type'] == ctype
        m = Matcher(P.get('comment_phrases') or [], P.get('use_default_rules', True), P.get('question_mark', True))
        target = int(P.get('max_videos') or 20)
        pages = max(1, min(int(P.get('comment_pages') or 2), 5))
        min_c, min_p = int(P.get('min_comments') or 1), int(P.get('min_plays') or 0)
        d_from, d_to = P.get('date_from') or '', P.get('date_to') or ''
        must = [w.lower() for w in P.get('must_words') or [] if w.strip()]
        excl = [w.lower() for w in P.get('exclude_words') or [] if w.strip()]
        seen = db.seen_codes(plat) if P.get('skip_existing', True) else set()
        mode = P.get('mode', 'keyword')
        srcs = []
        if mode in ('keyword', 'both'): srcs += [('kw', k.strip()) for k in P.get('keywords') or [] if k.strip()]
        if mode in ('hashtag', 'both'): srcs += [('tag', t.strip().lstrip('#')) for t in P.get('hashtags') or [] if t.strip()]
        if not srcs: raise RuntimeError('没有可用的关键词/标签')
        stopf = lambda: self._stop
        if plat == 'tiktok':
            from .tt import TT, parse_session
            if not cfg.get('tt_cookie'): raise Blocked('请先在「Cookie」页面填写 TikTok Cookie')
            cl = TT(parse_session(cfg['tt_cookie'], cfg.get('tt_ms_token'), cfg.get('tt_device_id'), cfg.get('tt_user_agent')),
                    float(cfg.get('tt_delay_min', 1.5)), float(cfg.get('tt_delay_max', 3)), self.log, stopf)
            self.set(stage='检查 TikTok 登录'); uid, un = cl.me(); self.log(f'TikTok 已登录 {un or uid}')
            tt_pages = max(1, min(int(P.get('tt_comment_pages') or 2), 50))
            ctype = 'video'
            def gen(kind, s):
                return cl.search(s if kind == 'kw' else '#' + s, int(P.get('search_pages') or 3), ('kw:' if kind == 'kw' else 'tag:#') + s)
            def comments(v):
                own = lambda c: c['user'] == v['account'] or (c.get('uid') and c['uid'] == v.get('owner_id'))
                cs = cl.comments(v, tt_pages, until=lambda L: any(m.is_q(c['text'], c['user'], v['account']) and not own(c) for c in L))
                return [c for c in cs if not own(c)]
            def done():
                from . import config as _c
                if cl.S['ms_token'] != cfg.get('tt_ms_token'): _c.save({'tt_ms_token': cl.S['ms_token']})
        elif plat == 'facebook':
            if not cfg.get('fb_cookie'): raise Blocked('请先在「Cookie」页面填写 Facebook Cookie')
            from .fb import FB
            from . import config
            cl = FB(cfg['fb_cookie'], float(cfg.get('fb_delay_min', 1.5)), float(cfg.get('fb_delay_max', 3)), self.log, stopf,
                    on_cookie=lambda ck: config.save({'fb_cookie': ck}), docs=cfg.get('fb_docs') or None)
            self.set(stage='登录 Facebook'); self.log(f'Facebook 已登录 USER_ID={cl.login()}')
            tabs = {'video': ['videos'], 'post': ['posts'], 'both': ['videos', 'posts']}[ctype]
            def gen(kind, s):
                q = s if kind == 'kw' else '#' + s
                for tab in tabs:
                    yield from cl.search(q, tab, int(P.get('search_pages') or 3), ('kw:' if kind == 'kw' else 'tag:#') + s)
            fetch_views = P.get('fb_fetch_views', True)
            fb_pages = max(1, min(int(P.get('fb_comment_pages') or 2), 50))
            def comments(v):
                own = lambda c: c['user'] == v['account'] or (c.get('uid') and c['uid'] == v.get('owner_id'))
                hit = lambda L: any(m.is_q(c['text'], c['user'], v['account']) and not own(c) for c in L)
                cs, ref = [], v['url']
                if '/reel/' not in v['url']:   # reel pages carry no comments/views in HTML -> go straight to GraphQL
                    cs, plays, _cur, ref = cl.post_page(v)
                    if plays is not None and fetch_views: v['plays'] = plays; v['plays_known'] = True
                if not hit(cs) and v.get('media_id'):
                    cs += cl.gql_comments(v, fb_pages, ref, until=hit)
                seen_ = set(); out = []
                for c in cs:
                    if (c['user'], c['text']) not in seen_ and not own(c): seen_.add((c['user'], c['text'])); out.append(c)
                return out
            def done(): config.save({'fb_docs': cl.export_docs()})
        else:
            if not cfg.get('cookie'): raise Blocked('请先在「Cookie」页面填写 Instagram Cookie')
            cl = IG(cfg['cookie'], float(cfg.get('delay_min', 1.5)), float(cfg.get('delay_max', 3)), self.log, stopf)
            def gen(kind, s):
                return cl.keyword_media(s, int(P.get('search_pages') or 4)) if kind == 'kw' else cl.tag_media(s)
            def comments(v):
                return cl.comments(v['shortcode'], pages, until=lambda L: any(m.is_q(c['text'], c['user'], v['account']) for c in L))
            def done(): pass
        PN = {'instagram': 'Instagram', 'facebook': 'Facebook', 'tiktok': 'TikTok'}[plat]
        CN = {'video': '视频', 'post': '帖子', 'both': '视频+帖子'}[ctype]
        local = set()
        self.log(f'开始：{PN} · {CN} · {len(srcs)} 个搜索源，目标 {target} 条有提问的内容')
        try:
            for kind, s in srcs:
                if self._stop or self.state['matched'] >= target: break
                self.set(stage=f'{PN} 搜索 {"关键词 " if kind=="kw" else "标签 #"}{s}')
                for v in gen(kind, s):
                    if self._stop or self.state['matched'] >= target: break
                    code = v['shortcode']
                    if not code or code in local: continue
                    local.add(code)
                    if not want(v) or v['comment_count'] < max(1, min_c): continue
                    if v.get('plays_known') and (v['plays'] or 0) < min_p: continue
                    if d_from and v['publish_date'] and v['publish_date'] < d_from or d_to and v['publish_date'] and v['publish_date'] > d_to: continue
                    cap = (v['caption'] + ' ' + v['account']).lower()
                    if must and not any(w in cap for w in must): continue
                    if excl and any(w in cap for w in excl): continue
                    if code in seen:
                        with self.lock: self.state['skipped'] += 1
                        continue
                    with self.lock: self.state['candidates'] += 1
                    self.set(stage='检查评论区', current=v['url'])
                    cs = comments(v)
                    if self._stop and not cs: break
                    q = [c for c in cs if m.is_q(c['text'], c['user'], v['account'])]
                    with self.lock: self.state['scanned'] += 1
                    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    db.mark_seen(plat, code, len(q), now)
                    if plat == 'facebook' and min_p and v.get('plays_known') and (v['plays'] or 0) < min_p:
                        self.log(f'— 播放量不足 {v["plays"]} {v["url"]}'); continue
                    if not q:
                        self.log(f'— 无提问 {v["account"]} {v["url"]} (看了 {len(cs)} 条)'); continue
                    v.update(question_count=len(q), scanned_comments=len(cs), crawled_at=now, run_id=rid,
                             sample_questions=' || '.join(f"@{c['user']}: {c['text'][:150]}" for c in q[:3]),
                             caption=(v['caption'] or '')[:300].replace('\n', ' '))
                    db.upsert(v)
                    with self.lock: self.state['matched'] += 1
                    self.log(f'✅ [{PN}/{"视频" if v["content_type"]=="video" else "帖子"}] {v["account"]} 提问 {len(q)} 条 · {v["url"]}')
        finally:
            done()
        self.log(f'结束：匹配 {self.state["matched"]} 条，检查 {self.state["scanned"]} 条，跳过已有 {self.state["skipped"]} 条')
