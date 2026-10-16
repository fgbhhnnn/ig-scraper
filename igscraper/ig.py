"""Instagram web client (read-only GET requests only)."""
import json, re, time, random, datetime, uuid, requests
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'
APP_ID = '936619743392459'
REPLY_QH = '1ee91c32fc020d44158a3192eda98247'
COMMENT_QH = 'bc3296d1ce80a24b1b6e40b1e72903f5'
# 2026-10 起网页版关键词搜索改成 GraphQL（旧的 /api/v1/fbsearch/web/top_serp/ 和 topsearch 返回 404）
SERP_DOC = ('PolarisKeywordSearchExplorePageRelayQuery', '37324993597144881')
SERP_DOC_PAGE = ('PolarisKeywordSearchExplorePageRelayPaginationQuery', '28656899673911396')
# 免登录可用：按 shortcode 取帖子/Reel 详情（含视频地址、点赞、评论数、文案）
POST_DOC = ('PolarisPostRootQuery', '28188170744199537')
POST_PV = ['AdDebugToolEnabled', 'MultiCaptionCarouselEnabled', 'ReelsRecoDebugOverlayEnabled', 'ShortDramaEnabled',
           'SuggestedUserFeedUnitCardsEnabled', 'ThreadsStyleCommentsEnabled']
ASBD_ID = '359341'   # 网页 JS 里 BDHeaderConfig.ASBD_ID 的常量（2026-10）；运行时会尝试从 JS 更新
# 运行时从 JS 包里发现的 doc_id / 常量（进程内缓存）
DISCOVERED = {}

def jazoest(tok):
    """网页 DTSGUtils.getNumericValue：'2' + 各字符编码之和（登录用 fb_dtsg，未登录用 lsd）"""
    return '2' + str(sum(ord(c) for c in tok or ''))

def js_urls(html):
    return list(dict.fromkeys(u.replace('\\/', '/') for u in re.findall(
        r'https:(?:\\/\\/|//)static\.(?:cdninstagram\.com|xx\.fbcdn\.net)(?:\\/|/)rsrc\.php[^"\'\s]+?\.js[^"\'\s]*', html)))

def scan_js(text, want, suffix='_instagramRelayOperation'):
    """从一个 JS 包里找 doc_id（__d("XQuery_instagramRelayOperation",[],…exports="123")）和 ASBD_ID"""
    out = {}
    for m in re.finditer(r'__d\("(\w+?)' + suffix + r'",\[\],\(function\([^)]*\)\{\w\.exports="(\d+)"', text):
        if m.group(1) in want: out[m.group(1)] = m.group(2)
    m = re.search(r'__d\("BDHeaderConfig",\[\],\(function\([^)]*\)\{"use strict";var \w="(\d+)"', text)
    if m: out['_asbd'] = m.group(1)
    return out

def page_app_id(html):
    m = re.search(r'"X-IG-App-ID":"(\d+)"', html) or re.search(r'"APP_ID":"(\d+)"', html)
    return m.group(1) if m else ''

class Blocked(Exception): pass

def doc_stale(o, status):
    """像是 doc_id 过期（持久化查询找不到 / 403 Page Not Found）"""
    if status in (403, 404) and not o: return True
    if not isinstance(o, dict) or o.get('data'): return False
    msg = json.dumps(o.get('errors') or o)[:500].lower()
    return 'persisted' in msg or 'doc_id' in msg or 'document' in msg or 'not found' in msg

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
        from .tt import sys_proxies
        self.proxies = sys_proxies()
        if self.proxies: self.s.proxies.update(self.proxies)
        self.last_err = ''; self.tok = {}; self._cs = None

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
                self.last_err = f'网络/代理错误：{e.__class__.__name__}: {str(e)[:160]}'
                self.log(self.last_err); self._sleep(5); continue
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
                self.last_err = f'HTTP {r.status_code}（{path}）'; self.log(f'{r.status_code} {path} {head[:120]}'); return None
            if r.status_code != 200:
                self.last_err = f'HTTP {r.status_code}（{path}）' + ('：接口不存在（Instagram 已下线该接口）' if r.status_code == 404 else '')
                self.log(f'HTTP {r.status_code} {path} {head[:120]}'); return None
            if not r.content: self.last_err = f'空响应（{path}）'; self.log(self.last_err); return None
            try: return r.json()
            except Exception:
                if 'not-logged-in' in head or '/accounts/login' in head: raise Blocked('返回了登录页，Cookie 已失效')
                self.last_err = f'返回的不是 JSON（{path}，HTTP {r.status_code}）'; self.log(self.last_err); return None
        if not self.last_err: self.last_err = '多次重试仍失败'
        return None

    def check(self):
        """返回登录的用户名；失败时抛出带具体原因的 Blocked"""
        d = self.get('/api/v1/accounts/edit/web_form_data/', pace=False)
        u = ((d or {}).get('form_data') or {}).get('username')
        if u: return u
        e1 = self.last_err
        try: r = self.s.get('https://www.instagram.com/', timeout=30)
        except Exception as e: raise Blocked(f'无法连接 Instagram（网络/代理错误：{e.__class__.__name__}）。{e1}')
        m = re.search(r'"username":"([\w.]+)"', r.text)
        if m and '"viewerId"' in r.text or m and 'not-logged-in' not in r.text[:3000] and '"actorID":"' in r.text: return m.group(1)
        if 'not-logged-in' in r.text[:3000] or '/accounts/login' in r.url: raise Blocked('Cookie 已失效（Instagram 显示未登录），请重新导出')
        raise Blocked(f'校验失败：{e1 or "接口无返回"}；首页 HTTP {r.status_code}')

    def diag(self):
        """逐项检查：Cookie 字段、代理、出口 IP、登录接口、搜索（GraphQL）、标签接口"""
        out = []
        need = [k for k in ('sessionid', 'ds_user_id', 'csrftoken') if not cookie_get(self.ck, k)]
        out.append('Cookie 字段：' + ('✅ sessionid / ds_user_id / csrftoken 齐全' if not need else '❌ 缺少 ' + '、'.join(need)))
        out.append(f'代理：{self.proxies["https"] if self.proxies else "未检测到系统代理（直连）"}')
        try:
            ip = self.cs().get('https://api.ipify.org?format=json', timeout=15).json().get('ip')
            out.append(f'出口 IP：{ip}')
        except Exception as e: out.append(f'出口 IP：❌ 获取失败（{e.__class__.__name__}，代理可能不通）')
        try: out.append(f'登录：✅ {self.check()}')
        except Exception as e: out.append(f'登录：❌ {e}')
        try:
            n = 0
            for _ in self.keyword_media('handbag', 1): n += 1
            out.append(f'关键词搜索（GraphQL）：{"✅" if n else "❌"} {n} 条' + ('' if n else f'（{self.last_err}）'))
        except Exception as e: out.append(f'关键词搜索：❌ {e}')
        d = self.get('/api/v1/tags/web_info/', {'tag_name': 'handbag'}, pace=False)
        out.append('标签接口：' + ('✅ 正常' if d and d.get('data') else f'❌ {self.last_err}'))
        return out

    def cs(self):
        """GraphQL 用浏览器指纹（curl_cffi），普通 requests 会被返回 HTML"""
        if self._cs is None:
            from curl_cffi import requests as cr
            self._cs = cr.Session(impersonate='chrome')
            self._cs.headers.update({'Cookie': self.ck, 'X-IG-App-ID': APP_ID, 'X-CSRFToken': cookie_get(self.ck, 'csrftoken')})
            if self.proxies: self._cs.proxies = self.proxies
        return self._cs

    def _tokens(self, kw):
        """GraphQL 需要页面里的 fb_dtsg / lsd / actorID"""
        if self.tok: return self.tok
        r = self.cs().get('https://www.instagram.com/explore/search/keyword/', params={'q': kw}, timeout=30)
        t = r.text; g = lambda p: (re.search(p, t) or [None, ''])[1]
        self.tok = {'fb_dtsg': g(r'"DTSGInitialData",\[\],\{"token":"([^"]+)'), 'lsd': g(r'"LSD",\[\],\{"token":"([^"]+)'), 'av': g(r'"actorID":"(\d+)"')}
        self.page_html = t
        aid = page_app_id(t)
        if aid and aid != self.cs().headers.get('X-IG-App-ID'): self.cs().headers['X-IG-App-ID'] = aid; self.log(f'IG app-id 更新为 {aid}')
        if not self.tok['fb_dtsg']:
            if 'not-logged-in' in t[:3000]: raise Blocked('Cookie 已失效（Instagram 显示未登录），请重新导出')
            self.tok = {}; raise RuntimeError(f'搜索页没拿到 fb_dtsg（HTTP {r.status_code}）')
        return self.tok

    def discover(self, html, want, limit=600):
        """从页面引用的 JS 包（静态 CDN）里找最新 doc_id；只在内置值失效时调用，结果进程内缓存。
        Relay 查询模块一般在列表末尾，所以倒序、并发扫描。"""
        want = set(want) - set(DISCOVERED)
        if not want: return {}
        from concurrent.futures import ThreadPoolExecutor
        urls = js_urls(html)[::-1][:limit]; found = {}
        def one(u):
            if self.stop() or want <= set(found): return
            try: found.update(scan_js(self.cs().get(u, timeout=20).text, want))
            except Exception: pass
        with ThreadPoolExecutor(6) as ex: list(ex.map(one, urls))
        DISCOVERED.update(found)
        self.log(f'IG doc_id 自动发现（{len(urls)} 个 JS 包）：' + (str(found) if found else '未找到，继续用内置值'))
        return found

    @staticmethod
    def doc(d):
        return (d[0], DISCOVERED.get(d[0], d[1]))

    def gql(self, doc, variables, ref, _retry=True):
        tk = self._tokens(variables.get('query', ''))
        self._sleep(random.uniform(self.dmin, self.dmax))
        doc0 = doc; doc = self.doc(doc)
        data = {'av': tk['av'], '__user': '0', '__a': '1', '__comet_req': '7', 'fb_dtsg': tk['fb_dtsg'], 'jazoest': jazoest(tk['fb_dtsg']),
                'lsd': tk['lsd'], 'fb_api_caller_class': 'RelayModern', 'fb_api_req_friendly_name': doc[0], 'variables': json.dumps(variables),
                'server_timestamps': 'true', 'doc_id': doc[1]}
        h = {'X-FB-LSD': tk['lsd'], 'X-FB-Friendly-Name': doc[0], 'X-ASBD-ID': DISCOVERED.get('_asbd', ASBD_ID), 'Referer': ref,
             'Origin': 'https://www.instagram.com', 'Content-Type': 'application/x-www-form-urlencoded'}
        for t in range(3):
            try: r = self.cs().post('https://www.instagram.com/api/graphql', data=data, headers=h, timeout=40)
            except Exception as e: self.last_err = f'网络/代理错误：{e.__class__.__name__}'; self.log(self.last_err); self._sleep(5); continue
            if r.status_code == 429: w = 60 * (t + 1); self.log(f'429 限流，等待 {w}s'); self._sleep(w); continue
            head = r.text[:600]
            if 'checkpoint_required' in head or 'challenge_required' in head: raise Blocked('Instagram 要求安全验证(checkpoint)，已停止。请在浏览器里处理后重新导出 Cookie')
            try: o = r.json()
            except Exception: self.last_err = f'GraphQL 返回的不是 JSON（HTTP {r.status_code}）'; self.log(self.last_err); o = None
            if _retry and doc_stale(o, r.status_code) and self.discover(getattr(self, 'page_html', ''), [SERP_DOC[0], SERP_DOC_PAGE[0], doc0[0]]).get(doc0[0], doc[1]) != doc[1]:
                return self.gql(doc0, variables, ref, _retry=False)
            return o
        return None

    def public_media(self, code):
        """免登录取帖子详情（GraphQL PolarisPostRootQuery，只需页面里的 lsd）。返回 media dict 或 None"""
        from curl_cffi import requests as cr
        s = cr.Session(impersonate='chrome')
        if self.proxies: s.proxies = self.proxies
        ref = f'https://www.instagram.com/p/{code}/'
        t = s.get(ref, timeout=30).text
        lsd = (re.search(r'"LSD",\[\],\{"token":"([^"]+)', t) or [None, ''])[1]
        if not lsd: self.last_err = '免登录：帖子页没拿到 lsd'; return None
        aid = page_app_id(t) or APP_ID
        for attempt in range(2):
            doc = self.doc(POST_DOC)
            v = dict({f'__relay_internal__pv__Polaris{k}relayprovider': False for k in POST_PV}, shortcode=code)
            d = {'av': '0', '__user': '0', '__a': '1', '__comet_req': '7', 'lsd': lsd, 'jazoest': jazoest(lsd), 'fb_api_caller_class': 'RelayModern',
                 'fb_api_req_friendly_name': doc[0], 'variables': json.dumps(v), 'server_timestamps': 'true', 'doc_id': doc[1]}
            h = {'X-FB-LSD': lsd, 'X-IG-App-ID': aid, 'X-ASBD-ID': DISCOVERED.get('_asbd', ASBD_ID), 'X-FB-Friendly-Name': doc[0], 'Referer': ref, 'Origin': 'https://www.instagram.com'}
            r = s.post('https://www.instagram.com/graphql/query', data=d, headers=h, timeout=30)
            try: o = r.json()
            except Exception: o = None
            its = ((((o or {}).get('data') or {}).get('xdt_api__v1__media__shortcode__web_info') or {}).get('items')) or []
            if its: return its[0]
            self.last_err = f'免登录详情失败（HTTP {r.status_code}）：{(r.text or "")[:120]}'
            if attempt or not doc_stale(o, r.status_code): return None
            if self.discover(t, [POST_DOC[0]]).get(POST_DOC[0], doc[1]) == doc[1]: return None
        return None

    @staticmethod
    def serp_medias(o):
        out = []
        def walk(x):
            if isinstance(x, dict):
                if x.get('code') and x.get('pk') and ('taken_at' in x or 'media_type' in x): out.append(x); return
                for v in x.values(): walk(v)
            elif isinstance(x, list):
                for v in x: walk(v)
        walk(o); return out

    # ---------- media sources ----------
    @staticmethod
    def norm(i, source):
        code = i.get('code')
        cap = ((i.get('caption') or {}).get('text') or '')
        return {'shortcode': code, 'media_id': str(i.get('pk') or i.get('id') or ''),
                'account': (i.get('user') or {}).get('username', ''),
                'url': f"https://www.instagram.com/{'reel' if i.get('product_type') == 'clips' or (i.get('media_type') == 2 and not i.get('product_type')) else 'p'}/{code}/",
                'caption': cap, 'plays': i.get('play_count') or i.get('ig_play_count') or i.get('view_count') or 0,
                'likes': i.get('like_count') or 0, 'comment_count': i.get('comment_count') or 0,
                'taken_at': i.get('taken_at') or 0,
                'publish_date': datetime.datetime.fromtimestamp(i['taken_at']).strftime('%Y-%m-%d') if i.get('taken_at') else '',
                'source': source, 'cover': (((i.get('image_versions2') or {}).get('candidates') or [{}])[-1]).get('url', ''), 'is_video': i.get('media_type') == 2,
                'platform': 'instagram', 'content_type': 'video' if i.get('media_type') == 2 else 'post',
                'plays_known': any(i.get(k) is not None for k in ('play_count', 'ig_play_count', 'view_count'))}

    def keyword_media(self, kw, max_pages=0):
        """网页版关键词搜索（GraphQL）；失败时退回旧 REST 接口。max_pages=0 表示翻到底（最多 100 页）"""
        ref = 'https://www.instagram.com/explore/search/keyword/?q=' + requests.utils.quote(kw)
        sid = str(uuid.uuid4()); after = None; pg = 0; total = 0; seen = set()
        try:
            while not max_pages or pg < max_pages:
                if self.stop(): return
                o = self.gql(SERP_DOC_PAGE if after else SERP_DOC, {'after': after, 'first': 24, 'query': kw, 'search_session_id': sid, 'serp_session_id': sid}, ref)
                d = ((o or {}).get('data') or {}).get('xdt_fbsearch__top_serp_graphql')
                if d is None:
                    if pg == 0: raise RuntimeError(self.last_err or json.dumps(o)[:200])
                    self.log(f'IG 搜索「{kw}」第{pg+1}页失败：{self.last_err or json.dumps(o)[:150]}'); return
                pg += 1
                ms = [m for m in self.serp_medias(d.get('edges')) if m['code'] not in seen]
                seen.update(m['code'] for m in ms); total += len(ms)
                self.log(f'IG 搜索「{kw}」第{pg}页 {len(ms)} 条')
                for m in ms: yield self.norm(m, 'kw:' + kw)
                pi = d.get('page_info') or {}
                if not pi.get('has_next_page') or not pi.get('end_cursor') or (not ms and pg > 1):
                    self.log(f'IG 搜索「{kw}」结果已到底（共 {pg} 页 {total} 条）'); return
                if pg >= 100: return
                after = pi['end_cursor']
            return
        except Blocked: raise
        except Exception as e:
            if pg: return
            self.log(f'IG GraphQL 搜索不可用（{str(e)[:120]}），改用旧接口')
        yield from self.keyword_media_rest(kw, max_pages)

    def keyword_media_rest(self, kw, max_pages=0):
        """max_pages=0 表示翻到底（最多 100 页）"""
        p = {'query': kw, 'enable_metadata': 'true'}; pg = 0; total = 0
        while not max_pages or pg < max_pages:
            if self.stop(): return
            d = self.get('/api/v1/fbsearch/web/top_serp/', p)
            if not d: self.log(f'IG 搜索「{kw}」第{pg+1}页请求失败，换下一个搜索词'); return
            pg += 1
            mg = d.get('media_grid')
            if not mg: self.log(f'关键词「{kw}」无视频结果' if pg == 1 else f'IG 搜索「{kw}」结果已到底（共 {pg-1} 页 {total} 条）'); return
            ms = [m['media'] for sec in mg.get('sections', []) for m in (sec.get('layout_content', {}).get('medias') or []) if m.get('media')]
            total += len(ms); self.log(f'IG 搜索「{kw}」第{pg}页 {len(ms)} 条')
            for m in ms: yield self.norm(m, 'kw:' + kw)
            if not mg.get('has_more') or not mg.get('next_max_id'):
                self.log(f'IG 搜索「{kw}」结果已到底（共 {pg} 页 {total} 条）'); return
            if pg >= 100: return
            p = {'query': kw, 'enable_metadata': 'true', 'rank_token': mg.get('rank_token'), 'next_max_id': mg.get('next_max_id'),
                 'reels_max_id': mg.get('reels_max_id'), 'page_index': pg}

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
