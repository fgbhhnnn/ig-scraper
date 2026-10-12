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
        ig = IG(cfg['cookie'], float(cfg.get('delay_min', 1.5)), float(cfg.get('delay_max', 3)), self.log, lambda: self._stop)
        if not ig.ck: raise Blocked('请先在「Cookie」页面填写 Cookie')
        m = Matcher(P.get('comment_phrases') or [], P.get('use_default_rules', True), P.get('question_mark', True))
        target = int(P.get('max_videos') or 20)
        pages = max(1, min(int(P.get('comment_pages') or 2), 5))
        min_c, min_p = int(P.get('min_comments') or 1), int(P.get('min_plays') or 0)
        d_from, d_to = P.get('date_from') or '', P.get('date_to') or ''
        must = [w.lower() for w in P.get('must_words') or [] if w.strip()]
        excl = [w.lower() for w in P.get('exclude_words') or [] if w.strip()]
        skip = P.get('skip_existing', True)
        seen = db.seen_codes() if skip else set()
        mode = P.get('mode', 'keyword')
        sources = []
        if mode in ('keyword', 'both'): sources += [('kw', k) for k in P.get('keywords') or [] if k.strip()]
        if mode in ('hashtag', 'both'): sources += [('tag', t) for t in P.get('hashtags') or [] if t.strip()]
        if not sources: raise RuntimeError('没有可用的关键词/标签')
        local = set()
        self.log(f'开始：{len(sources)} 个搜索源，目标 {target} 条有提问的视频')
        for kind, s in sources:
            if self._stop or self.state['matched'] >= target: break
            self.set(stage=f'搜索 {"关键词" if kind=="kw" else "标签 #"}{s}')
            gen = ig.keyword_media(s, int(P.get('search_pages') or 4)) if kind == 'kw' else ig.tag_media(s)
            for v in gen:
                if self._stop or self.state['matched'] >= target: break
                code = v['shortcode']
                if not code or code in local: continue
                local.add(code)
                if not v['is_video'] or v['comment_count'] < max(1, min_c) or (v['plays'] or 0) < min_p: continue
                if d_from and v['publish_date'] < d_from or d_to and v['publish_date'] > d_to: continue
                cap = (v['caption'] + ' ' + v['account']).lower()
                if must and not any(w in cap for w in must): continue
                if excl and any(w in cap for w in excl): continue
                if code in seen:
                    with self.lock: self.state['skipped'] += 1
                    continue
                with self.lock: self.state['candidates'] += 1
                self.set(stage='检查评论区', current=v['url'])
                cs = ig.comments(code, pages, until=lambda L: any(m.is_q(c['text'], c['user'], v['account']) for c in L))
                q = [c for c in cs if m.is_q(c['text'], c['user'], v['account'])]
                with self.lock: self.state['scanned'] += 1
                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                db.mark_seen(code, len(q), now)
                if not q:
                    self.log(f'— 无提问 {v["account"]} {v["url"]} (看了 {len(cs)} 条)'); continue
                v.update(question_count=len(q), scanned_comments=len(cs), crawled_at=now, run_id=rid,
                         sample_questions=' || '.join(f"@{c['user']}: {c['text'][:150]}" for c in q[:3]),
                         caption=v['caption'][:300].replace('\n', ' '))
                db.upsert(v)
                with self.lock: self.state['matched'] += 1
                self.log(f'✅ {v["account"]} 提问 {len(q)} 条 · {v["url"]}')
        self.log(f'结束：匹配 {self.state["matched"]} 条，检查 {self.state["scanned"]} 条，跳过已有 {self.state["skipped"]} 条')
