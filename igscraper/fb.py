"""Facebook web client (read-only: page GETs + read GraphQL queries only)."""
import json, re, time, random, datetime, urllib.parse, requests
from .ig import Blocked

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
CH = {'sec-ch-ua': '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"', 'sec-ch-ua-mobile': '?0',
      'sec-ch-ua-platform': '"Windows"', 'Accept-Language': 'en-US,en;q=0.9', 'User-Agent': UA}
DOC_FALLBACK = {'SearchCometResultsPaginatedResultsQuery': '29179353588360939',
                'CommentsListComponentsPaginationQuery': '40120064807592280',
                'CommentListComponentsRootQuery': '38863170746661819'}
WANT_DOCS = set(DOC_FALLBACK)
# provider variables Relay passes implicitly; server rejects the pagination query without them
PV_FALLBACK = ['CometUFICommentAutoTranslationType', 'CometUFICommentAvatarStickerAnimatedImage',
               'CometUFICommentActionLinksRewriteEnabled', 'IsWorkUser']
def pv_vars(names):
    return {f'__relay_internal__pv__{n}relayprovider': ('ORIGINAL' if n.endswith('TranslationType') else False) for n in names}

def walk(o, f):
    if isinstance(o, dict):
        f(o)
        for v in o.values(): walk(v, f)
    elif isinstance(o, list):
        for v in o: walk(v, f)

def blobs(t, need=None):
    for m in re.finditer(r'<script type="application/json"[^>]*>(.*?)</script>', t, re.S):
        if need and need not in m.group(1): continue
        try: yield json.loads(m.group(1))
        except Exception: pass

def parse_cookie(raw):
    from .ig import parse_cookie as p
    return p(raw)

class FB:
    def __init__(self, cookie, dmin=1.5, dmax=3.0, log=print, stop=lambda: False, on_cookie=None, docs=None):
        self.log, self.stop, self.on_cookie = log, stop, on_cookie
        self.dmin, self.dmax = dmin, dmax
        self.s = requests.Session(); self.tok = {}; self.uid = None; self.n = 0
        docs = dict(docs or {})
        self.pv = [x for x in (docs.pop('_pv', '') or '').split(',') if x] or list(PV_FALLBACK)
        self.docs = dict(DOC_FALLBACK); self.docs.update(docs); self.docs_scraped = bool(docs)
        for kv in parse_cookie(cookie).split(';'):
            if '=' in kv:
                k, v = kv.strip().split('=', 1); self.s.cookies.set(k, v, domain='.facebook.com')

    def cookie_str(self):
        d = {}
        for c in self.s.cookies:
            if 'facebook.com' in (c.domain or ''): d[c.name] = c.value
        return '; '.join(f'{k}={v}' for k, v in d.items())
    def _saved(self):
        if self.on_cookie:
            try: self.on_cookie(self.cookie_str())
            except Exception: pass
    def _sleep(self, sec):
        end = time.time() + sec
        while time.time() < end and not self.stop(): time.sleep(0.2)
    def _pace(self):
        if self.n: self._sleep(random.uniform(self.dmin, self.dmax))
        self.n += 1

    @staticmethod
    def logged_out(text, url):
        return ('/login' in url or '/checkpoint' in url or '"USER_ID":"0"' in text
                or '"queryName":"useCometLogInFormQuery"' in text)

    def nav(self, url, ref=None):
        for t in range(3):
            if self.stop(): return None
            self._pace()
            h = dict(CH, **{'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                            'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'same-origin' if ref else 'none',
                            'Sec-Fetch-Dest': 'document', 'Sec-Fetch-User': '?1', 'Upgrade-Insecure-Requests': '1'})
            if ref: h['Referer'] = ref
            try: r = self.s.get(url, headers=h, timeout=40)
            except Exception as e: self.log(f'FB 网络错误: {e}'); self._sleep(8); continue
            self._saved()
            if r.status_code == 429: w = 90 * (t + 1); self.log(f'FB 429 限流，等待 {w}s'); self._sleep(w); continue
            if self.logged_out(r.text, r.url): raise Blocked(f'Facebook 登录失效或需要验证（{r.url[:80]}），已停止')
            if r.status_code != 200: self.log(f'FB HTTP {r.status_code} {url}'); return None
            return r
        return None

    def login(self):
        r = self.nav('https://www.facebook.com/')
        if not r: raise Blocked('无法打开 Facebook 首页')
        t = r.text
        m = re.search(r'"USER_ID":"(\d+)"', t)
        if not m or m.group(1) == '0': raise Blocked('Facebook 未登录（USER_ID=0），请重新导出 Cookie')
        self.uid = m.group(1)
        g = lambda p: (re.search(p, t) or [None, ''])[1]
        self.tok = dict(fb_dtsg=g(r'"DTSGInitialData",\[\],\{"token":"([^"]+)'), lsd=g(r'"LSD",\[\],\{"token":"([^"]+)'),
                        jazoest=g(r'jazoest=(\d+)'), __spin_r=g(r'"__spin_r":(\d+)'), __spin_t=g(r'"__spin_t":(\d+)'),
                        __rev=g(r'"server_revision":(\d+)'))
        return self.uid

    def export_docs(self):
        return dict(self.docs, _pv=','.join(self.pv))

    def scrape_docs(self, html, limit=120):
        """Find doc_ids for wanted queries in the page's JS bundles (best effort)."""
        if self.docs_scraped: return
        self.docs_scraped = True
        js = list(dict.fromkeys(re.findall(r'"(https://static\.xx\.fbcdn\.net/rsrc\.php/[^"]+\.js[^"]*)"', html.replace('\\/', '/'))))
        found = {}; pv_ok = False
        for j in js[:limit]:
            if self.stop() or (WANT_DOCS <= set(found) and pv_ok): break
            try: c = requests.get(j, headers={'User-Agent': UA}, timeout=20).text
            except Exception: continue
            for m in re.finditer(r'__d\("(\w+Query)_facebookRelayOperation".{0,200}?exports="(\d+)"', c):
                if m.group(1) in WANT_DOCS: found[m.group(1)] = m.group(2)
            i = c.find('__d("CommentsListComponentsPaginationQuery.graphql"')
            if i >= 0:
                j = c.find('__d(', i + 10); pv = sorted(set(re.findall(r'__relay_internal__pv__(\w+?)relayprovider', c[i:j if j > 0 else None])))
                if pv: self.pv = pv; pv_ok = True; self.log(f'FB 评论翻页 provider 变量: {pv}')
        self.docs.update(found)
        self.log(f'FB doc_id：从 {min(len(js), limit)} 个 JS 包中找到 {len(found)} 个' + (f' {found}' if found else '，使用内置默认值'))

    def gql(self, name, v, ref):
        if self.stop(): return []
        self._pace()
        d = dict(av=self.uid, __user=self.uid, __a='1', __comet_req='15', __spin_b='trunk', fb_api_caller_class='RelayModern',
                 fb_api_req_friendly_name=name, variables=json.dumps(v), server_timestamps='true', doc_id=self.docs[name], **self.tok)
        h = dict(CH, **{'Content-Type': 'application/x-www-form-urlencoded', 'X-FB-Friendly-Name': name, 'X-FB-LSD': self.tok['lsd'],
                        'X-ASBD-ID': '129477', 'Origin': 'https://www.facebook.com', 'Referer': ref, 'Sec-Fetch-Site': 'same-origin',
                        'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty', 'Accept': '*/*'})
        try: r = self.s.post('https://www.facebook.com/api/graphql/', data=d, headers=h, timeout=40)
        except Exception as e: self.log(f'FB GraphQL 网络错误: {e}'); return []
        self._saved()
        if '/login' in r.url or '"error":1357001' in r.text: raise Blocked('Facebook GraphQL 返回未登录，已停止')
        out = []
        for ln in r.text.splitlines():
            try: out.append(json.loads(ln))
            except Exception: pass
        if not out: self.log(f'FB GraphQL {name} 无有效返回: {r.text[:120]}')
        return out

    # ---------- parse ----------
    @staticmethod
    def row(edge, source):
        vm = (edge.get('rendering_strategy') or {}).get('view_model') or {}
        s_ = vm.get('story') or (vm.get('click_model') or {}).get('story') or {}
        if not s_: return None
        st = json.dumps(s_)
        g = lambda p: (re.search(p, st) or [None, ''])[1]
        fb = s_.get('feedback') or {}; own = fb.get('owning_profile') or {}
        url = g(r'"permalink_url": "([^"]+)"') or g(r'"url": "(https://www\.facebook\.com/[^"]+/(?:posts|videos|reel)/[^"]+)"')
        if not url and own.get('id') and s_.get('post_id'): url = f"https://www.facebook.com/{own['id']}/posts/{s_['post_id']}"
        if not url: return None
        try: cap = json.loads('"' + g(r'"message": \{"text": "((?:[^"\\]|\\.)*)"') + '"')
        except Exception: cap = ''
        num = lambda x: int(x) if x and x.isdigit() else 0
        att = [((a or {}).get('media') or {}).get('__typename') for a in (s_.get('attachments') or [])]
        is_vid = '/reel/' in url or '/videos/' in url or '/watch' in url or 'Video' in att
        ct = s_.get('creation_time') or num(g(r'"creation_time": (\d+)'))
        pid = str(s_.get('post_id') or g(r'"post_id": "(\d+)"') or url)
        return {'platform': 'facebook', 'shortcode': pid, 'media_id': fb.get('id', ''), 'account': own.get('name') or '',
                'owner_id': own.get('id') or '', 'url': url, 'caption': cap, 'plays': 0,
                'likes': num(g(r'"reaction_count": \{"count": (\d+)')), 'comment_count': num(g(r'"comments": \{"total_count": (\d+)')),
                'taken_at': ct, 'publish_date': datetime.datetime.fromtimestamp(ct).strftime('%Y-%m-%d') if ct else '',
                'source': source, 'is_video': is_vid, 'content_type': 'video' if is_vid else 'post', 'plays_known': False}

    def search(self, q, tab='videos', max_pages=3, source=None):
        """tab: videos | posts. Yields normalized rows."""
        source = source or 'kw:' + q
        if not self.uid: self.login()
        su = f'https://www.facebook.com/search/{tab}/?q=' + urllib.parse.quote(q)
        r = self.nav(su, 'https://www.facebook.com/')
        if not r: return
        t = r.text; self.scrape_docs(t)
        edges, cur = [], [None]
        def f(d):
            if 'serpResponse' in d:
                res = d['serpResponse']['results']; edges.extend(res.get('edges') or [])
                pi = res.get('page_info') or {}; cur[0] = (pi.get('end_cursor'), pi.get('has_next_page'))
        for b in blobs(t, 'serpResponse'): walk(b, f)
        self.log(f'FB 搜索「{q}」({"视频" if tab=="videos" else "帖子"}) 第1页 {len(edges)} 条')
        for e in edges:
            x = self.row(e, source)
            if x: yield x
        i = t.find('"queryName":"SearchCometResultsInitialResultsQuery"')
        if i < 0: return
        j = t.rfind('"variables":', 0, i)
        try: v = json.loads(t[j + 12:i - 1])
        except Exception: self.log('FB 搜索分页变量解析失败'); return
        try: v['args']['experience']['client_defined_experiences'] = []
        except Exception: pass
        c = cur[0]
        for _ in range(max_pages - 1):
            if not (c and c[0] and c[1]) or self.stop(): return
            v['cursor'] = c[0]
            o = self.gql('SearchCometResultsPaginatedResultsQuery', v, su)
            edges.clear(); cur[0] = None; walk(o, f); c = cur[0]
            n = 0; rows = [x for x in (self.row(e, source) for e in edges) if x]
            self.log(f'FB 搜索「{q}」翻页 {len(rows)} 条')
            for x in rows: n += 1; yield x
            if not n: return

    def post_page(self, item):
        """Fetch post page: returns (comments[{user,text}], plays, end_cursor). First ~10 comments come in HTML."""
        u = f"https://www.facebook.com/{item['owner_id']}/posts/{item['shortcode']}" if item.get('owner_id') and item['shortcode'].isdigit() else item['url']
        r = self.nav(u, 'https://www.facebook.com/')
        if not r: return [], None, None, u
        t = r.text; cs = []; cur = [None]
        def f(d):
            if d.get('__typename') == 'Comment' and isinstance(d.get('body'), dict):
                a = d.get('author') or {}; cs.append({'user': a.get('name') or '', 'uid': a.get('id') or '', 'text': (d['body'].get('text') or '').replace('\n', ' ')})
            tl = d.get('top_level_comments') if isinstance(d.get('top_level_comments'), dict) else None
            if tl and (tl.get('page_info') or {}).get('end_cursor'): cur[0] = tl['page_info']['end_cursor']
        for b in blobs(t, 'Comment'): walk(b, f)
        m = re.search(r'"play_count":(\d+)', t) or re.search(r'"video_view_count":(\d+)', t)
        seen = set(); out = []
        for c in cs:
            k = (c['user'], c['text'])
            if k not in seen: seen.add(k); out.append(c)
        return out, (int(m.group(1)) if m else None), cur[0], u

    @staticmethod
    def _parse_comments(o):
        cs, pi = [], [None]
        def f(d):
            if d.get('__typename') == 'Comment' and isinstance(d.get('body'), dict):
                a = d.get('author') or {}
                cs.append({'user': a.get('name') or '', 'uid': a.get('id') or '', 'text': (d['body'].get('text') or '').replace('\n', ' ')})
            c = d.get('comment_rendering_instance_for_feed_location')
            if isinstance(c, dict) and isinstance(c.get('comments'), dict) and c['comments'].get('page_info'):
                pi[0] = c['comments']['page_info']
        walk(o, f)
        p = pi[0] or {}
        return cs, (p.get('end_cursor') if p.get('has_next_page') else None)

    def root_comments(self, item, intent=None, ref=None):
        """CommentListComponentsRootQuery by feedback id -> (comments, next_cursor)."""
        v = {'commentsIntentToken': intent, 'feedLocation': 'TAHOE', 'feedbackSource': 65, 'focusCommentID': None,
             'scale': 1, 'useDefaultActor': False, 'id': item['media_id']}
        return self._parse_comments(self.gql('CommentListComponentsRootQuery', v, ref or item['url']))

    def page_comments(self, item, cursor, ref=None, intent=None):
        """CommentsListComponentsPaginationQuery: ~10 top-level comments per page -> (comments, next_cursor)."""
        v = {'commentsAfterCount': -1, 'commentsAfterCursor': cursor, 'commentsBeforeCount': None, 'commentsBeforeCursor': None,
             'commentsIntentToken': intent, 'feedLocation': 'TAHOE', 'focusCommentID': None, 'scale': 1,
             'useDefaultActor': False, 'id': item['media_id'], **pv_vars(self.pv)}
        o = self.gql('CommentsListComponentsPaginationQuery', v, ref or item['url'])
        cs, nxt = self._parse_comments(o)
        if not cs and 'missing_required_variable_value' in json.dumps(o)[:2000]:
            self.log('FB 评论翻页失败：缺少必需变量（Facebook 可能更新了接口），本条只用首屏评论')
        return cs, nxt

    def gql_comments(self, item, max_pages=2, ref=None, until=None):
        """Root query + up to max_pages-1 pagination pages; stops early when until(list) is True."""
        cs, cur = self.root_comments(item, None, ref)
        for _ in range(max(0, max_pages - 1)):
            if not cur or self.stop() or (until and until(cs)): break
            more, cur = self.page_comments(item, cur, ref)
            if not more: break
            cs += more
        return cs
