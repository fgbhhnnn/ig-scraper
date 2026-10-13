"""评论爬取任务: crawl comments for selected DB items or pasted URLs (IG / FB / TikTok), read-only."""
import datetime, re, time
from . import db, config
from .task import Task
from .ig import IG, Blocked
from .matcher import Matcher, DEFAULT_SPAM
from .langdet import detect

def detect_platform(url):
    u = url.lower()
    if 'instagram.com' in u: return 'instagram'
    if 'facebook.com' in u or 'fb.watch' in u or 'fb.com' in u: return 'facebook'
    if 'tiktok.com' in u: return 'tiktok'
    return None

class CommentTask(Task):
    def _crawl(self, cfg, P, rid):
        items = list(P.get('items') or [])      # from DB
        for u in P.get('urls') or []:
            u = u.strip()
            if not u: continue
            pl = detect_platform(u)
            if not pl: self.log(f'无法识别平台，跳过：{u}'); continue
            items.append({'platform': pl, 'url': u, '_resolve': True})
        if not items: raise RuntimeError('没有要爬取的内容：请在结果页勾选，或粘贴链接')
        max_c = int(P.get('max_comments') or 0); max_p = int(P.get('max_pages') or 0)
        if max_c <= 0: max_c = 10**9
        if max_p <= 0: max_p = 10**6
        self.log(f"每条最多评论：{'全部' if max_c >= 10**9 else max_c}；最多翻页：{'不限' if max_p >= 10**6 else max_p}")
        replies = bool(P.get('replies', True))
        m = Matcher(P.get('phrases') or [], True, True)
        spam = re.compile(DEFAULT_SPAM, re.I)
        self.set(target=len(items))
        clients = {}
        stopf = lambda: self._stop
        def client(pl):
            if pl in clients: return clients[pl]
            if pl == 'instagram':
                if not cfg.get('cookie'): raise Blocked('缺少 Instagram Cookie')
                c = IG(cfg['cookie'], float(cfg['delay_min']), float(cfg['delay_max']), self.log, stopf)
            elif pl == 'facebook':
                if not cfg.get('fb_cookie'): raise Blocked('缺少 Facebook Cookie')
                from .fb import FB
                c = FB(cfg['fb_cookie'], float(cfg['fb_delay_min']), float(cfg['fb_delay_max']), self.log, stopf,
                       on_cookie=lambda ck: config.save({'fb_cookie': ck}), docs=cfg.get('fb_docs') or None)
                self.log(f'Facebook 已登录 USER_ID={c.login()}')
            else:
                if not cfg.get('tt_cookie'): raise Blocked('缺少 TikTok Cookie')
                from .tt import TT, parse_session
                c = TT(parse_session(cfg['tt_cookie'], cfg.get('tt_ms_token'), cfg.get('tt_device_id'), cfg.get('tt_user_agent')),
                       float(cfg['tt_delay_min']), float(cfg['tt_delay_max']), self.log, stopf)
                uid, un = c.me(); self.log(f'TikTok 已登录 {un or uid}')
            clients[pl] = c; return c
        total = 0
        for n, it in enumerate(items, 1):
            if self._stop: break
            pl = it['platform']; PN = {'instagram': 'Instagram', 'facebook': 'Facebook', 'tiktok': 'TikTok'}[pl]
            self.set(stage=f'{PN} 评论 {n}/{len(items)}', current=it.get('url', ''))
            blocked = None; cs = []; c = None
            post_id = it.get('shortcode') or ''; account = it.get('account', ''); url = it.get('url', '')
            try:
                c = client(pl)
                c.partial = []
                if pl == 'instagram':
                    code = it.get('shortcode') or (re.search(r'/(?:p|reel|reels|tv)/([\w-]+)', it['url']) or [None, None])[1]
                    if not code: self.log(f'无法识别 IG 链接：{it["url"]}'); continue
                    cs, owner = c.comments_full(code, max_p, max_c, replies)
                    post_id, account = code, it.get('account') or owner
                    url = it.get('url') if not it.get('_resolve') else f'https://www.instagram.com/p/{code}/'
                elif pl == 'facebook':
                    if it.get('_resolve'): it = dict(it, **c.resolve(it['url']))
                    cs = c.gql_comments(it, max_p, it['url'])
                    if replies is False: cs = [x for x in cs if not x.get('is_reply')]
                    cs = cs[:max_c]; post_id, account, url = it['shortcode'], it.get('account', ''), it['url']
                else:
                    if it.get('_resolve'): it = dict(it, **c.resolve(it['url']))
                    cs = c.comments_full(it, max_p, max_c, replies)
                    post_id, account, url = it['shortcode'], it.get('account', ''), it['url']
            except Blocked as e:
                blocked = e; cs = list(getattr(c, 'partial', None) or [])
                if not cs: raise
                self.log(f'⚠️ 平台限制/风控，本条已抓到的 {len(cs)} 条评论先保存')
                if pl == 'instagram' and not post_id: post_id = (re.search(r'/(?:p|reel|reels|tv)/([\w-]+)', url) or [None, ''])[1]
                if pl == 'instagram' and it.get('_resolve'): url = f'https://www.instagram.com/p/{post_id}/'
                cs = cs[:max_c]
            except Exception as e:
                self.log(f'❌ {it.get("url")} 失败：{e}'); continue
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'); rows = []
            for x in cs:
                code_, lname, region = detect(x['text'])
                is_author = int(bool(account) and (x['user'] == account or (x.get('uid') and x.get('uid') == it.get('owner_id'))))
                rows.append({'platform': pl, 'comment_id': x.get('id') or f"{post_id}:{x['user']}:{hash(x['text'])}", 'post_id': post_id,
                             'post_url': url, 'account': account, 'commenter': x['user'], 'text': x['text'], 'lang': code_,
                             'lang_name': lname, 'region': region, 'likes': int(x.get('likes') or 0),
                             'ctime': datetime.datetime.fromtimestamp(int(x['time'])).strftime('%Y-%m-%d %H:%M') if x.get('time') else '',
                             'is_reply': int(x.get('is_reply') or 0), 'is_author': is_author, 'is_spam': int(bool(spam.search(x['text'].lower()))),
                             'matched': int(m.is_q(x['text'], x['user'], account)), 'crawled_at': now, 'run_id': rid})
            db.upsert_comments(rows); total += len(rows)
            with self.lock: self.state['scanned'] += 1; self.state['matched'] = total
            self.log(f'✅ [{PN}] {account or "-"} {url} 评论 {len(rows)} 条（回复 {sum(r["is_reply"] for r in rows)}）')
            if blocked: raise blocked
        if 'facebook' in clients: config.save({'fb_docs': clients['facebook'].export_docs()})
        if 'tiktok' in clients and clients['tiktok'].S['ms_token'] != cfg.get('tt_ms_token'): config.save({'tt_ms_token': clients['tiktok'].S['ms_token']})
        self.log(f'结束：{self.state["scanned"]}/{len(items)} 个内容，共 {total} 条评论')
