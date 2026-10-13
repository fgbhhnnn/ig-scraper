"""TikTok web client (read-only GETs)."""
import json, re, time, random, datetime, urllib.parse
from .ig import Blocked, parse_cookie
from . import ttsign

DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
RATE_CODES = {2484, 10201, 10202, 10203, 10204, 10205, 10206, 2483}

def parse_session(raw_cookie, ms_token='', device_id='', user_agent=''):
    ck = parse_cookie(raw_cookie)
    C = {}
    for kv in ck.split(';'):
        if '=' in kv:
            k, v = kv.strip().split('=', 1); C[k] = v     # last msToken wins (newest)
    did = (device_id or '').strip()
    if did.startswith('{'):      # pasted __tea_cache_tokens_1988 JSON
        try: did = str(json.loads(did).get('web_id') or '')
        except Exception: did = ''
    return {'cookie': ck, 'ms_token': (ms_token or '').strip() or C.get('msToken', ''), 'device_id': did,
            'user_agent': (user_agent or '').strip() or DEFAULT_UA,
            'odin': urllib.parse.unquote(C.get('multi_sids', '')).split(':')[0], 'verify_fp': C.get('s_v_web_id', ''),
            'logged_in': bool(C.get('sessionid') or C.get('sid_tt'))}

class TT:
    def __init__(self, sess, dmin=1.5, dmax=3.0, log=print, stop=lambda: False):
        from curl_cffi import requests as creq
        self.creq = creq; self.S = sess; self.log, self.stop = log, stop; self.dmin, self.dmax = dmin, dmax; self.n = 0
        ua = sess['user_agent']; m = re.search(r'Chrome/(\d+)', ua); v = m.group(1) if m else '129'
        self.H = {'User-Agent': ua, 'Cookie': sess['cookie'], 'Accept': '*/*', 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                  'sec-ch-ua': f'"Google Chrome";v="{v}", "Not_A Brand";v="8", "Chromium";v="{v}"', 'sec-ch-ua-platform': '"Windows"',
                  'sec-ch-ua-mobile': '?0', 'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin', 'priority': 'u=1, i'}
        self.wit = str(int(time.time()))

    def _sleep(self, s):
        end = time.time() + s
        while time.time() < end and not self.stop(): time.sleep(0.2)
    def _http(self, url, ref):
        return self.creq.get(url, headers=dict(self.H, Referer=ref), timeout=30, impersonate='chrome', default_headers=False, http_version='v2')

    def base(self, extra, ref, from_page, app_lang='zh-Hans'):
        S = self.S
        p = dict(WebIdLastTime=self.wit, aid='1988', app_language=app_lang, app_name='tiktok_web', browser_language='zh-CN',
                 browser_name='Mozilla', browser_online='true', browser_platform='Win32', browser_version=S['user_agent'].split('Mozilla/', 1)[-1],
                 channel='tiktok_web', cookie_enabled='true', data_collection_enabled='true', device_id=S['device_id'], device_platform='web_pc',
                 focus_state='true', from_page=from_page, history_len='3', is_fullscreen='false', is_page_visible='true', odinId=S['odin'] or S['device_id'],
                 os='windows', priority_region='SG', referer=ref, region='SG', root_referer=ref, screen_height='1080', screen_width='1920',
                 tz_name='Asia/Shanghai', user_is_login='true', verifyFp=S['verify_fp'], webcast_language='zh-Hans')
        p.update(extra)
        return urllib.parse.urlencode(sorted(p.items()), quote_via=lambda s, *a, **k: urllib.parse.quote(s, safe=''))

    def api(self, path, extra, ref, from_page, app_lang='zh-Hans'):
        if not self.S['ms_token']: raise Blocked('TikTok 缺少 msToken：请在 Cookie 页填写（浏览器 F12 → Application → Session Storage → msToken）')
        if not self.S['device_id']: raise Blocked('TikTok 缺少 device_id：请填写 localStorage 里 __tea_cache_tokens_1988 的 web_id')
        empty = 0
        for t in range(4):
            if self.stop(): return None
            if self.n: self._sleep(random.uniform(self.dmin, self.dmax))
            self.n += 1
            url = ttsign.signed_url(path, self.base(extra, ref, from_page, app_lang), self.S['ms_token'], self.S['user_agent'], ref)
            try: r = self._http(url, ref)
            except Exception as e: self.log(f'TikTok 网络错误: {e}'); self._sleep(5); continue
            nt = r.headers.get('x-ms-token')
            if nt and len(nt) > 100: self.S['ms_token'] = nt
            if r.status_code == 429:
                w = 60 * (t + 1); self.log(f'TikTok 429 限流，等待 {w}s'); self._sleep(w); continue
            if not r.content:
                empty += 1
                if empty >= 2: raise Blocked('TikTok 返回空响应（被风控/签名失效）。请重新导出完整 Cookie、msToken 和 device_id 后再试')
                self.log('TikTok 返回空响应，等待 30s 后重试'); self._sleep(30); continue
            try: d = r.json()
            except Exception: self.log(f'TikTok 非 JSON 响应 HTTP {r.status_code}'); return None
            sc = d.get('status_code', d.get('statusCode', 0))
            if sc in RATE_CODES:
                w = 60 * (t + 1)
                self.log(f'TikTok 风控/限流 status_code={sc}（{d.get("status_msg","")}），等待 {w}s')
                if t >= 2: raise Blocked(f'TikTok 连续风控 status_code={sc}：请检查 Cookie 是否完整（含 sessionid）、device_id 是否与该浏览器一致，或稍后再试')
                self._sleep(w); continue
            if sc == 8 or (sc and 'login' in str(d.get('status_msg', '')).lower()):
                raise Blocked('TikTok 登录失效，请重新导出 Cookie')
            return d
        return None

    def me(self):
        r = self._http('https://www.tiktok.com/passport/web/account/info/?aid=1988&app_name=tiktok_web&device_platform=web_pc', 'https://www.tiktok.com/')
        try: d = r.json().get('data') or {}
        except Exception: d = {}
        if not d.get('user_id_str'): raise Blocked('TikTok 未登录：Cookie 需包含 sessionid（Cookie-Editor 导出 JSON 即可）')
        return d.get('user_id_str'), d.get('username') or d.get('screen_name') or ''

    @staticmethod
    def norm(i, source):
        a = i.get('author') or {}; st = i.get('stats') or i.get('statsV2') or {}
        n = lambda x: int(x) if str(x).isdigit() else 0
        ct = n(i.get('createTime'))
        return {'platform': 'tiktok', 'shortcode': str(i['id']), 'media_id': str(i['id']), 'account': a.get('uniqueId', ''),
                'owner_id': a.get('id', ''), 'url': f"https://www.tiktok.com/@{a.get('uniqueId','')}/video/{i['id']}",
                'caption': i.get('desc') or '', 'plays': n(st.get('playCount')), 'likes': n(st.get('diggCount')),
                'comment_count': n(st.get('commentCount')), 'shares': n(st.get('shareCount')), 'taken_at': ct,
                'publish_date': datetime.datetime.fromtimestamp(ct).strftime('%Y-%m-%d') if ct else '',
                'source': source, 'is_video': True, 'content_type': 'video', 'plays_known': True}

    def search(self, kw, max_pages=3, source=None):
        ref = 'https://www.tiktok.com/search?q=' + urllib.parse.quote(kw)
        off, cur = 0, '0'
        for pg in range(max_pages):
            d = self.api('/api/search/general/full/', dict(keyword=kw, offset=str(off), count='12', cursor=cur,
                         is_non_personalized_search='0', device_type='web_h265'), ref, 'search')
            if not d: return
            items = [x['item'] for x in (d.get('data') or []) if x.get('type') == 1 and x.get('item')]
            self.log(f'TikTok 搜索「{kw}」第{pg+1}页 {len(items)} 条')
            for i in items: yield self.norm(i, source or 'kw:' + kw)
            if not d.get('has_more'): return
            cur = str(d.get('cursor') or off + 12); off = int(cur) if cur.isdigit() else off + 12

    def comments(self, item, max_pages=2, until=None):
        ref = item['url']; cur = '0'; out = []
        for _ in range(max_pages):
            d = self.api('/api/comment/list/', dict(aweme_id=item['shortcode'], count='20', cursor=cur, current_region='SG',
                         enter_from='tiktok_web', fromWeb='1', is_non_personalized='false'), ref, 'video', 'ja-JP')
            if not d: break
            for c in d.get('comments') or []:
                u = c.get('user') or {}
                out.append({'user': u.get('unique_id') or u.get('nickname') or '', 'uid': u.get('uid', ''), 'text': (c.get('text') or '').replace('\n', ' ')})
            if (until and until(out)) or not d.get('has_more'): break
            cur = str(d.get('cursor'))
        return out

    def resolve(self, url):
        """Pasted TikTok URL (incl. vm./vt. short links) -> item dict."""
        if not re.search(r'/video/\d+', url):
            r = self.creq.get(url, headers={'User-Agent': self.S['user_agent']}, impersonate='chrome', allow_redirects=True, timeout=30)
            url = r.url
        m = re.search(r'tiktok\.com/@([^/?#]+)/(?:video|photo)/(\d+)', url)
        if not m: raise RuntimeError(f'无法识别的 TikTok 链接：{url}')
        return {'platform': 'tiktok', 'shortcode': m.group(2), 'media_id': m.group(2), 'account': m.group(1),
                'url': f'https://www.tiktok.com/@{m.group(1)}/video/{m.group(2)}', 'caption': '', 'content_type': 'video'}

    def comments_full(self, item, max_pages=5, max_comments=200, replies=False, max_reply_threads=10):
        ref = item['url']; cur = '0'; out = []; threads = []; pg = 0; self.partial = out
        if max_comments >= 10**9: max_reply_threads = 10**9
        for _ in range(max_pages):
            if self.stop() or len(out) >= max_comments: break
            d = self.api('/api/comment/list/', dict(aweme_id=item['shortcode'], count='20', cursor=cur, current_region='SG',
                         enter_from='tiktok_web', fromWeb='1', is_non_personalized='false'), ref, 'video', 'ja-JP')
            if not d: break
            for c in d.get('comments') or []:
                u = c.get('user') or {}
                out.append({'id': str(c.get('cid')), 'user': u.get('unique_id') or u.get('nickname') or '', 'uid': u.get('uid', ''),
                            'text': (c.get('text') or '').replace('\n', ' '), 'likes': c.get('digg_count') or 0,
                            'time': c.get('create_time') or 0, 'is_reply': 0})
                if (c.get('reply_comment_total') or 0) > 0: threads.append(str(c.get('cid')))
            pg += 1
            if pg % 5 == 0: self.log(f'  TikTok 已翻 {pg} 页，{len(out)} 条评论…')
            nc = str(d.get('cursor'))
            if not d.get('has_more') or not d.get('comments') or nc == cur: break
            cur = nc
        if replies:
            unlimited = max_comments >= 10**9
            for i, cid in enumerate(threads[:max_reply_threads], 1):
                if self.stop() or len(out) >= max_comments: break
                rc = '0'
                for _ in range(50 if unlimited else 1):
                    d = self.api('/api/comment/list/reply/', dict(item_id=item['shortcode'], comment_id=cid, count='20', cursor=rc), ref, 'video', 'ja-JP')
                    for c in (d or {}).get('comments') or []:
                        u = c.get('user') or {}
                        out.append({'id': str(c.get('cid')), 'user': u.get('unique_id') or '', 'uid': u.get('uid', ''),
                                    'text': (c.get('text') or '').replace('\n', ' '), 'likes': c.get('digg_count') or 0,
                                    'time': c.get('create_time') or 0, 'is_reply': 1})
                    nc = str((d or {}).get('cursor'))
                    if not d or not d.get('has_more') or not d.get('comments') or nc == rc or self.stop(): break
                    rc = nc
                if i % 10 == 0: self.log(f'  TikTok 回复：已读 {i}/{len(threads)} 个楼，共 {len(out)} 条…')
        return out[:max_comments]
