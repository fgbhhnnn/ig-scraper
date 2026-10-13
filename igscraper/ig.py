"""Instagram web client (read-only GET requests only)."""
import json, re, time, random, datetime, requests
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'
APP_ID = '936619743392459'
REPLY_QH = '1ee91c32fc020d44158a3192eda98247'
COMMENT_QH = 'bc3296d1ce80a24b1b6e40b1e72903f5'

class Blocked(Exception): pass

def parse_cookie(raw):
    """Accept 'a=b; c=d' header string or Cookie-Editor JSON array/object. Returns header string."""
    raw = (raw or '').strip()
    if not raw: return ''
    if raw[0] in '[{':
        d = json.loads(raw)
        if isinstance(d, dict): d = d.get('cookies', [d]) if 'name' not in d else [d]
        return '; '.join(f"{c['name']}={c['value']}" for c in d if c.get('name'))
    raw = re.sub(r'^cookie:\s*', '', raw, flags=re.I)
    return '; '.join(p.strip() for p in raw.replace('\n', ';').split(';') if '=' in p)

def cookie_get(ck, name):
    m = re.search(r'(?:^|;\s*)' + re.escape(name) + r'=([^;]*)', ck)
    return m.group(1) if m else ''

class IG:
    def __init__(self, cookie, dmin=1.5, dmax=3.0, log=print, stop=lambda: False):
        self.ck = parse_cookie(cookie); self.dmin, self.dmax = dmin, dmax; self.log = log; self.stop = stop
        self.s = requests.Session()
        self.s.headers.update({'Cookie': self.ck, 'X-IG-App-ID': APP_ID, 'X-CSRFToken': cookie_get(self.ck, 'csrftoken'),
                               'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest', 'Referer': 'https://www.instagram.com/'})
        self.user_id = cookie_get(self.ck, 'ds_user_id')

    def _sleep(self, sec):
        end = time.time() + sec
        while time.time() < end and not self.stop(): time.sleep(0.2)

    def get(self, path, params=None, pace=True):
        for t in range(3):
            if self.stop(): return None
            if pace: self._sleep(random.uniform(self.dmin, self.dmax))
            try:
                r = self.s.get('https://www.instagram.com' + path, params=params, timeout=30, allow_redirects=False)
            except Exception as e:
                self.log(f'网络错误: {e}'); self._sleep(5); continue
            head = r.text[:800]
            loc = r.headers.get('Location', '')
            if r.status_code in (301, 302) and ('login' in loc or 'challenge' in loc or 'checkpoint' in loc):
                raise Blocked(f'被重定向到 {loc}（登录失效或需要验证）')
            if 'checkpoint_required' in head or '"challenge"' in head or 'challenge_required' in head:
                raise Blocked('Instagram 要求安全验证(checkpoint)，已停止。请在浏览器里处理后重新导出 Cookie')
            if r.status_code == 429:
                w = 60 * (t + 1); self.log(f'429 限流，等待 {w}s'); self._sleep(w); continue
            if r.status_code in (401, 403):
                if 'login_required' in head or 'require_login' in head:
                    raise Blocked('登录失效(login_required)，请重新填写 Cookie')
                self.log(f'{r.status_code} {path} {head[:120]}'); return None
            if r.status_code != 200:
                self.log(f'HTTP {r.status_code} {path} {head[:120]}'); return None
            try: return r.json()
            except Exception:
                if 'login' in head.lower(): raise Blocked('返回了登录页，Cookie 已失效')
                self.log(f'非 JSON 响应 {path}'); return None
        return None

    def check(self):
        d = self.get('/api/v1/web/search/topsearch/', {'query': 'instagram', 'context': 'blended'}, pace=False)
        return bool(d and ('users' in d or 'hashtags' in d))

    # ---------- media sources ----------
    @staticmethod
    def norm(i, source):
        code = i.get('code')
        cap = ((i.get('caption') or {}).get('text') or '')
        return {'shortcode': code, 'media_id': str(i.get('pk') or i.get('id') or ''),
                'account': (i.get('user') or {}).get('username', ''),
                'url': f"https://www.instagram.com/{'reel' if i.get('product_type') == 'clips' else 'p'}/{code}/",
                'caption': cap, 'plays': i.get('play_count') or i.get('ig_play_count') or i.get('view_count') or 0,
                'likes': i.get('like_count') or 0, 'comment_count': i.get('comment_count') or 0,
                'taken_at': i.get('taken_at') or 0,
                'publish_date': datetime.datetime.fromtimestamp(i['taken_at']).strftime('%Y-%m-%d') if i.get('taken_at') else '',
                'source': source, 'is_video': i.get('media_type') == 2,
                'platform': 'instagram', 'content_type': 'video' if i.get('media_type') == 2 else 'post', 'plays_known': True}

    def keyword_media(self, kw, max_pages=5):
        p = {'query': kw, 'enable_metadata': 'true'}
        for pg in range(max_pages):
            d = self.get('/api/v1/fbsearch/web/top_serp/', p)
            if not d: return
            mg = d.get('media_grid')
            if not mg: self.log(f'关键词「{kw}」无视频结果'); return
            for s in mg.get('sections', []):
                for m in (s.get('layout_content', {}).get('medias') or []):
                    if m.get('media'): yield self.norm(m['media'], 'kw:' + kw)
            if not mg.get('has_more'): return
            p = {'query': kw, 'enable_metadata': 'true', 'rank_token': mg.get('rank_token'), 'next_max_id': mg.get('next_max_id'),
                 'reels_max_id': mg.get('reels_max_id'), 'page_index': pg + 1}

    def tag_media(self, tag):
        tag = tag.lstrip('#').strip().replace(' ', '')
        d = self.get('/api/v1/tags/web_info/', {'tag_name': tag})
        if not d: return
        for sec in ['top', 'recent']:
            for s in ((d.get('data') or {}).get(sec) or {}).get('sections', []):
                for m in (s.get('layout_content', {}).get('medias') or []):
                    if m.get('media'): yield self.norm(m['media'], 'tag:#' + tag)

    def comments(self, shortcode, max_pages=2, until=None):
        """Yield pages of comments; caller can stop early. until(list)->bool stops after a page."""
        cur, allc = None, []
        for _ in range(max_pages):
            var = {'shortcode': shortcode, 'first': 50}
            if cur: var['after'] = cur
            d = self.get('/graphql/query/', {'query_hash': COMMENT_QH, 'variables': json.dumps(var)})
            try: e = d['data']['shortcode_media']['edge_media_to_parent_comment']
            except Exception: break
            for n in e['edges']:
                nodes = [n['node']] + [r['node'] for r in (n['node'].get('edge_threaded_comments') or {}).get('edges', [])]
                for x in nodes: allc.append({'user': x['owner']['username'], 'text': x['text'].replace('\n', ' ')})
            if (until and until(allc)) or not e['page_info']['has_next_page']: break
            cur = e['page_info']['end_cursor']
        return allc

    @staticmethod
    def pk_of(shortcode):
        A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'; pk = 0
        for ch in shortcode[:11]: pk = pk * 64 + A.index(ch)
        return str(pk)

    def _v1(self, path, params):
        H = {'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Site': 'same-origin'}
        old = dict(self.s.headers); self.s.headers.update(H)
        try: return self.get(path, params)
        finally: self.s.headers.clear(); self.s.headers.update(old)

    def _v1_fill(self, shortcode, out, seen, max_comments, replies, unlimited):
        """Continue/fill comments through /api/v1/media/{pk}/comments/ (min_id paging) and child_comments for replies."""
        pk = self.pk_of(shortcode); mi = None; pg = 0; stale = 0; threads = []
        def add(x, rep):
            cid = str(x.get('pk') or x.get('id'))
            if cid in seen: return False
            seen.add(cid)
            out.append({'id': cid, 'user': (x.get('user') or {}).get('username', ''), 'text': (x.get('text') or '').replace('\n', ' '),
                        'likes': x.get('comment_like_count') or 0, 'time': x.get('created_at') or 0, 'is_reply': rep})
            return True
        while not self.stop() and len(out) < max_comments and pg < 2000:
            p = {'can_support_threading': 'true', 'permalink_enabled': 'false'}
            if mi: p['min_id'] = mi
            d = self._v1(f'/api/v1/media/{pk}/comments/', p)
            if not d: break
            n0 = len(out)
            for x in d.get('comments') or []:
                add(x, 0)
                if replies:
                    for r in x.get('preview_child_comments') or []: add(r, 1)
                    if (x.get('child_comment_count') or 0) > len(x.get('preview_child_comments') or []): threads.append(str(x['pk']))
            pg += 1; stale = stale + 1 if len(out) == n0 else 0
            if pg % 5 == 0: self.log(f'  IG(v1) 已翻 {pg} 页，共 {len(out)} 条评论…')
            nm = d.get('next_min_id')
            if not nm or nm == mi: break
            mi = nm
        if not replies: return
        threads = list(dict.fromkeys(threads))
        for i, cid in enumerate(threads, 1):
            if self.stop() or len(out) >= max_comments: break
            cur = None
            for _ in range(100 if unlimited else 5):
                p = {'max_id': cur} if cur else {}
                d = self._v1(f'/api/v1/media/{pk}/comments/{cid}/child_comments/', p)
                if not d: break
                for r in d.get('child_comments') or []: add(r, 1)
                nc = d.get('next_max_child_cursor')
                if not d.get('has_more_tail_child_comments') or not nc or nc == cur: break
                cur = nc
            if i % 20 == 0: self.log(f'  IG 回复：已读 {i}/{len(threads)} 个楼，共 {len(out)} 条…')

    def comments_full(self, shortcode, max_pages=4, max_comments=200, replies=True):
        """Rich comments: [{id,user,text,likes,time,is_reply}] incl. preview of threaded replies; also returns owner username."""
        cur, out, owner, pg = None, [], '', 0; self.partial = out; more = []; seen = set(); stale = 0; total = 0
        for _ in range(max_pages):
            if self.stop() or len(out) >= max_comments: break
            var = {'shortcode': shortcode, 'first': 50}
            if cur: var['after'] = cur
            d = self.get('/graphql/query/', {'query_hash': COMMENT_QH, 'variables': json.dumps(var)})
            try: sm = d['data']['shortcode_media']; e = sm['edge_media_to_parent_comment']
            except Exception: break
            owner = owner or ((sm.get('owner') or {}).get('username') or ''); total = max(total, e.get('count') or 0)
            n0 = len(out)
            for n in e['edges']:
                nodes = [(n['node'], 0)]
                tc = n['node'].get('edge_threaded_comments') or {}
                if replies: nodes += [(r['node'], 1) for r in tc.get('edges', [])]
                if replies and (tc.get('page_info') or {}).get('has_next_page'): more.append((n['node']['id'], tc['page_info'].get('end_cursor')))
                for x, rep in nodes:
                    if str(x['id']) in seen: continue
                    seen.add(str(x['id']))
                    out.append({'id': str(x['id']), 'user': x['owner']['username'], 'text': x['text'].replace('\n', ' '),
                                'likes': (x.get('edge_liked_by') or {}).get('count', 0), 'time': x.get('created_at') or 0, 'is_reply': rep})
            pg += 1; new = len(out) - n0; stale = stale + 1 if new == 0 else 0
            if pg % 5 == 0: self.log(f'  IG 已翻 {pg} 页，{len(out)} 条评论…')
            nc = e['page_info'].get('end_cursor')
            if not e['page_info']['has_next_page'] or not nc or nc == cur or not e['edges'] or stale >= 5: break
            cur = nc
        unlimited = max_comments >= 10**9
        if not self.stop() and len(out) < max_comments and total and len(out) < total:
            self.log(f'  IG GraphQL 拿到 {len(out)}/{total} 条，改用 v1 接口继续补齐…')
            self._v1_fill(shortcode, out, seen, max_comments, replies, unlimited)
            more = []
        more = list(dict(more).items())
        for i, (cid, rc) in enumerate(more, 1):
            if self.stop() or len(out) >= max_comments: break
            for _ in range(20):
                d = self.get('/graphql/query/', {'query_hash': REPLY_QH, 'variables': json.dumps({'comment_id': str(cid), 'first': 50, 'after': rc})})
                try: e = d['data']['comment']['edge_threaded_comments']
                except Exception: break
                for r in e['edges']:
                    x = r['node']
                    if str(x['id']) in seen: continue
                    seen.add(str(x['id']))
                    out.append({'id': str(x['id']), 'user': x['owner']['username'], 'text': x['text'].replace('\n', ' '),
                                'likes': (x.get('edge_liked_by') or {}).get('count', 0), 'time': x.get('created_at') or 0, 'is_reply': 1})
                nc = e['page_info'].get('end_cursor')
                if not e['page_info'].get('has_next_page') or not nc or nc == rc: break
                rc = nc
            if i % 10 == 0: self.log(f'  IG 回复：已读 {i}/{len(more)} 个楼，共 {len(out)} 条…')
        return out[:max_comments], owner
