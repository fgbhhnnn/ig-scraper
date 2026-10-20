"""点赞分析 / 主页粉丝·关注获取 / 裂变：只读 GET，AI 判断账号类型（品牌商/工厂/服务博主/个人）。"""
import base64, csv, io, json, os, random, re, sqlite3, threading, time, datetime, uuid
from . import db
from .ig import IG, Blocked

TYPES = ['品牌商', '工厂/供应商', '服务/博主', '个人', '不确定']
BIZ = ('品牌商', '工厂/供应商')
GAP = (12.0, 20.0)          # 两次 IG 请求之间随机间隔（秒）
REST_EVERY, REST_SEC = 150, (240, 420)   # 每约 150 个请求自动休息几分钟
AI_BATCH = 20
LIKERS_CAP_NOTE = 'Instagram 只返回约 100 个点赞用户（按其排序），不是全部点赞'

# ---------------- 解析 ----------------
def shortcode_to_pk(code):
    al = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    n = 0
    for ch in (code or '')[:11]:
        if ch not in al: return ''
        n = n * 64 + al.index(ch)
    return str(n) if code else ''

def norm_user(u):
    pk = str(u.get('pk') or u.get('pk_id') or u.get('id') or '')
    un = u.get('username') or ''
    return {'pk': pk, 'username': un, 'full_name': u.get('full_name') or '', 'pic_url': u.get('profile_pic_url') or '',
            'is_verified': 1 if u.get('is_verified') else 0, 'is_private': 1 if u.get('is_private') else 0,
            'profile_url': f'https://www.instagram.com/{un}/' if un else ''}

def parse_users(j):
    """friendships / likers 响应 -> (用户列表, next_max_id)"""
    us = [norm_user(u) for u in ((j or {}).get('users') or []) if isinstance(u, dict)]
    nxt = (j or {}).get('next_max_id')
    if nxt is not None and not (j or {}).get('has_more', True): nxt = None
    return [u for u in us if u['pk']], (str(nxt) if nxt not in (None, '') else None)

def dedupe(users, seen=None):
    seen = set() if seen is None else seen; out = []
    for u in users:
        if u['pk'] in seen: continue
        seen.add(u['pk']); out.append(u)
    return out

def is_private_empty(j, target_private=None):
    """私密账号（未关注）返回 200 + users=[] + has_more=false"""
    if target_private: return True
    j = j or {}
    return not (j.get('users') or []) and j.get('has_more') is False and j.get('next_max_id') is None

# ---------------- AI ----------------
PROMPT = ('你是外贸 B2B 线索分析员。下面是一批 Instagram 账号，每个账号给出用户名、昵称、是否认证、是否私密，以及头像图片（图片紧跟在对应编号后面）。\n'
          '请判断每个账号的类型，只能从这 5 个里选：品牌商、工厂/供应商、服务/博主、个人、不确定。\n'
          '- 品牌商：消费品牌、店铺、零售商、电商卖家\n- 工厂/供应商：制造商、批发、OEM/ODM、贸易公司、原材料供应\n'
          '- 服务/博主：化妆师、摄影师、设计师、网红/内容创作者、服务类个体\n- 个人：普通个人用户\n- 不确定：信息太少无法判断\n'
          '规则：头像是公司/商业 logo 或产品图的账号，必须归为「品牌商」或「工厂/供应商」（拿不准时归品牌商），不能归为「不确定」。'
          '用户名/昵称含 official、store、shop、factory、mfg、co、ltd、wholesale、bags、leather 等商业词也要重点考虑。真人自拍且名字像人名的通常是个人。\n'
          '只输出严格 JSON 数组，不要任何其他文字：[{"username":"...","type":"...","confidence":0到1的小数,"reason":"一句中文理由"}]')

def parse_ai_json(txt):
    """从模型输出里取 JSON 数组 -> {username: {type, confidence, reason}}"""
    t = re.sub(r'```(?:json)?', '', txt or '')
    m = re.search(r'\[.*\]', t, re.S)
    if not m: raise ValueError('模型没有返回 JSON 数组')
    arr = json.loads(m.group(0)); out = {}
    for x in arr:
        if not isinstance(x, dict) or not x.get('username'): continue
        ty = str(x.get('type') or '').strip()
        if ty not in TYPES:
            ty = next((k for k in TYPES if k.split('/')[0] in ty), '不确定')
        try: cf = round(float(x.get('confidence')), 2)
        except Exception: cf = None
        out[str(x['username']).lstrip('@')] = {'type': ty, 'confidence': cf, 'reason': str(x.get('reason') or '')[:200]}
    return out

def ai_batch(cfg, batch, chat=None):
    from . import vai
    chat = chat or vai.chat
    content = [{'type': 'text', 'text': PROMPT}]
    for i, u in enumerate(batch):
        content.append({'type': 'text', 'text': f"#{i+1} username={u['username']} full_name={u.get('full_name','')} verified={bool(u.get('is_verified'))} private={bool(u.get('is_private'))}"})
        if u.get('pic'): content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + u['pic']}})
    txt = chat(cfg['ai_base'], cfg['ai_key'], cfg['ai_model'], content, timeout=900)
    return parse_ai_json(txt)

def classify(cfg, users, log=print, stop=lambda: False, chat=None, on_batch=None):
    """分批（约 20 个）发给识图模型；被拒/超时自动对半拆分。返回 {username: result}"""
    res = {}; q = [users[i:i + AI_BATCH] for i in range(0, len(users), AI_BATCH)]
    while q and not stop():
        b = q.pop(0); t0 = time.time()
        try:
            r = ai_batch(cfg, b, chat); res.update(r)
            log(f'AI 判断 {len(b)} 个账号，用时 {time.time()-t0:.0f} 秒')
            if on_batch: on_batch(r)
        except Exception as e:
            if len(b) > 1:
                log(f'AI 这一批（{len(b)} 个）失败：{str(e)[:120]}，拆成两半重试'); q[:0] = [b[:len(b)//2], b[len(b)//2:]]
            else: log(f'AI 判断 @{b[0]["username"]} 失败：{str(e)[:120]}，标为不确定')
    return res

# ---------------- 存储 ----------------
UCOLS = ['job_id', 'pk', 'username', 'full_name', 'pic', 'is_verified', 'is_private', 'profile_url', 'type', 'confidence', 'reason', 'relation']
def init():
    with db._lock, db.conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS social_jobs(id TEXT PRIMARY KEY, kind TEXT, target TEXT, target_pk TEXT, chain TEXT, level INTEGER,
          parent TEXT, status TEXT, note TEXT, total INTEGER, created_at TEXT, url TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS social_users(job_id TEXT, pk TEXT, username TEXT, full_name TEXT, pic TEXT, is_verified INTEGER,
          is_private INTEGER, profile_url TEXT, type TEXT, confidence REAL, reason TEXT, relation TEXT, PRIMARY KEY(job_id, pk, relation))''')
        c.execute('CREATE TABLE IF NOT EXISTS ig_pk(username TEXT PRIMARY KEY, pk TEXT, is_private INTEGER)')
def mark_interrupted():
    """程序重启后，上次没跑完的任务标为已中断（结果保留）"""
    init()
    with db._lock, db.conn() as c: c.execute("UPDATE social_jobs SET status='已中断' WHERE status IN ('进行中','排队中')")
def remember_pk(username, pk, private=None):
    if not username or not pk: return
    with db._lock, db.conn() as c: c.execute('INSERT OR REPLACE INTO ig_pk VALUES(?,?,?)', (username.lower(), str(pk), private))
def known_pk(username):
    with db.conn() as c:
        r = c.execute('SELECT pk,is_private FROM ig_pk WHERE username=?', ((username or '').lower(),)).fetchone()
        return (r[0], r[1]) if r else (None, None)
def save_job(j):
    with db._lock, db.conn() as c:
        c.execute('INSERT OR REPLACE INTO social_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', [j.get(k) for k in
                  ('id', 'kind', 'target', 'target_pk', 'chain', 'level', 'parent', 'status', 'note', 'total', 'created_at', 'url')])
def update_job(jid, **kw):
    with db._lock, db.conn() as c: c.execute(f"UPDATE social_jobs SET {','.join(k+'=?' for k in kw)} WHERE id=?", list(kw.values()) + [jid])
def save_users(jid, users, relation):
    with db._lock, db.conn() as c:
        c.executemany(f"INSERT OR IGNORE INTO social_users({','.join(UCOLS)}) VALUES({','.join('?'*len(UCOLS))})",
                      [[jid, u['pk'], u['username'], u['full_name'], u.get('pic', ''), u['is_verified'], u['is_private'], u['profile_url'],
                        u.get('type'), u.get('confidence'), u.get('reason'), relation] for u in users])
def set_types(jid, res):
    with db._lock, db.conn() as c:
        for un, r in res.items():
            c.execute('UPDATE social_users SET type=?,confidence=?,reason=? WHERE job_id=? AND username=?', (r['type'], r['confidence'], r['reason'], jid, un))
def jobs():
    init()
    with db.conn() as c:
        out = []
        for r in c.execute('SELECT * FROM social_jobs ORDER BY created_at DESC'):
            d = dict(r)
            d['counts'] = {t: n for t, n in c.execute('SELECT COALESCE(type,"未判断"),COUNT(*) FROM social_users WHERE job_id=? GROUP BY 1', (d['id'],))}
            d['n'] = sum(d['counts'].values()); out.append(d)
        return out
def users(jid, typ=''):
    init()
    sql, a = 'SELECT * FROM social_users WHERE job_id=?', [jid]
    if typ == '商家': sql += " AND type IN ('品牌商','工厂/供应商')"
    elif typ == '未判断': sql += ' AND type IS NULL'
    elif typ: sql += ' AND type=?'; a.append(typ)
    order = "CASE type WHEN '品牌商' THEN 0 WHEN '工厂/供应商' THEN 1 WHEN '服务/博主' THEN 2 WHEN '个人' THEN 3 ELSE 4 END"
    with db.conn() as c: return [dict(r) for r in c.execute(sql + f' ORDER BY {order}, confidence DESC', a)]
def delete_job(jid):
    with db._lock, db.conn() as c: c.execute('DELETE FROM social_users WHERE job_id=?', (jid,)); c.execute('DELETE FROM social_jobs WHERE id=?', (jid,))
CSV_HEAD = [('username', '用户名'), ('full_name', '昵称'), ('profile_url', '主页链接'), ('type', 'AI 类型'), ('confidence', '置信度'), ('reason', '理由'),
            ('is_verified', '认证'), ('is_private', '私密'), ('relation', '关系'), ('chain', '来源链'), ('level', '层级')]
REL = {'likers': '点赞', 'followers': '粉丝', 'following': '关注'}
def export_csv(jids):
    s = io.StringIO(); w = csv.writer(s); w.writerow([h for _, h in CSV_HEAD])
    js = {j['id']: j for j in jobs()}
    for jid in jids:
        j = js.get(jid) or {}
        for u in users(jid):
            u = dict(u, chain=j.get('chain', ''), level=j.get('level', 0), relation=REL.get(u['relation'], u['relation']),
                     is_verified='是' if u['is_verified'] else '否', is_private='是' if u['is_private'] else '否')
            w.writerow([u.get(k, '') for k, _ in CSV_HEAD])
    return '\ufeff' + s.getvalue()

# ---------------- 任务 ----------------
class SocialTask:
    def __init__(self):
        self.lock = threading.Lock(); self.thread = None; self._stop = False; self.queue = []
        self.state = {'running': False, 'stage': '空闲', 'logs': [], 'requests': 0, 'error': None, 'current': '', 'queue': 0, 'job_id': None}
    def log(self, m):
        with self.lock: self.state['logs'] = (self.state['logs'] + [time.strftime('%H:%M:%S ') + str(m)])[-500:]
    def set(self, **kw):
        with self.lock: self.state.update(kw)
    def snapshot(self, since=0):
        with self.lock:
            s = dict(self.state); s['log_total'] = len(s['logs']); s['logs'] = s['logs'][since:] if since <= len(s['logs']) else s['logs']
            s['queue'] = len(self.queue); return s
    def stop(self): self._stop = True; self.log('收到停止指令，当前请求结束后停止（已获取的结果会保留）')
    def stopped(self): return self._stop

    def add(self, cfg, jobs_):
        """jobs_: [{kind:'likers', media_pk, url, target} | {kind:'followers'/'following', target(username), target_pk?, count, chain?, level?, parent?}]"""
        init(); ids = []
        for j in jobs_:
            j = dict(j); j['id'] = time.strftime('%Y%m%d%H%M%S-') + uuid.uuid4().hex[:5]
            j['created_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'); j['status'] = '排队中'
            j['level'] = int(j.get('level') or 0); j['chain'] = j.get('chain') or j.get('target') or ''
            save_job(j); self.queue.append(j); ids.append(j['id'])
        if not (self.thread and self.thread.is_alive()):
            self._stop = False
            with self.lock: self.state.update(running=True, stage='运行中', error=None)
            self.thread = threading.Thread(target=self._run, args=(cfg,), daemon=True); self.thread.start()
        return ids

    # ---- IG 请求（严格：429/验证/登录失效立即停止） ----
    def _ig(self, cfg):
        from . import config
        return IG(cfg['cookie'], 0, 0, self.log, self.stopped, on_cookie=lambda ck: config.save({'cookie': ck}))
    def _pace(self, ig):
        if self.state['requests']:
            if self.state['requests'] % REST_EVERY == 0:
                w = random.uniform(*REST_SEC); self.log(f'已连续请求 {self.state["requests"]} 次，自动休息 {w/60:.1f} 分钟，降低风控风险'); ig._sleep(w)
            else: ig._sleep(random.uniform(*GAP))
    def req(self, ig, path, ref='https://www.instagram.com/'):
        """浏览器指纹 + 完整请求头；429/401/403/验证/登录失效立即停止"""
        if self._stop: return None
        self._pace(ig)
        if self._stop: return None
        try: st, o, txt = ig.api(path, None, ref)
        finally:
            with self.lock: self.state['requests'] += 1
        if st != 200: self.log(f'HTTP {st}：{path[:60]}'); return None
        if o is None: raise Blocked('返回的不是数据（可能被登出），已停止')
        return o
    def lookup_uid(self, ig, un):
        """主页 HTML 取 uid；拿不到再用 web_profile_info（限流很严，只作最后手段）"""
        self._pace(ig)
        try: pk, priv = ig.profile_uid(un)
        finally:
            with self.lock: self.state['requests'] += 1
        if pk: return pk, priv
        self.log('主页里没找到 uid，改用 web_profile_info 接口')
        d = self.req(ig, f'/api/v1/users/web_profile_info/?username={un}', f'https://www.instagram.com/{un}/')
        u = ((d or {}).get('data') or {}).get('user') or {}
        return u.get('id'), u.get('is_private')
    def avatar(self, ig, url):
        b = ig.avatar(url)
        return base64.b64encode(b).decode() if b else ''

    def _run(self, cfg):
        ig = self._ig(cfg)
        try:
            while self.queue and not self._stop:
                j = self.queue.pop(0); self.set(job_id=j['id'], current=f"{REL.get(j['kind'], j['kind'])}：{j.get('chain')}")
                update_job(j['id'], status='进行中')
                try: n, note = self._do(cfg, ig, j)
                except Blocked:
                    update_job(j['id'], status='已中断'); raise
                update_job(j['id'], status='已停止' if self._stop else '完成', total=n, note=note)
        except Blocked as e: self.log('⛔ ' + str(e)); self.set(error=str(e)); self._fail_rest()
        except Exception as e: self.log(f'❌ 出错：{e}'); self.set(error=str(e)); self._fail_rest()
        finally:
            if self._stop: self._fail_rest('已停止')
            self.set(running=False, stage='已停止' if self._stop else ('出错' if self.state['error'] else '完成'), current='')
    def _fail_rest(self, st='未执行'):
        for q in self.queue: update_job(q['id'], status=st)
        self.queue.clear()

    def _do(self, cfg, ig, j):
        kind = j['kind']
        if kind == 'likers':
            pk = j.get('media_pk') or shortcode_to_pk(j.get('shortcode', ''))
            self.log(f'获取点赞用户：{j.get("url") or pk}（{LIKERS_CAP_NOTE}）')
            d = self.req(ig, f'/api/v1/media/{pk}/likers/', j.get('url') or 'https://www.instagram.com/')
            us, _ = parse_users(d); us = dedupe(us)
            self.log(f'拿到 {len(us)} 个点赞用户（帖子显示 {d.get("user_count") if d else "?"} 个赞）')
            return self._finish(cfg, ig, j, us, 'likers'), LIKERS_CAP_NOTE
        # followers / following
        un = (j.get('target') or '').strip().lstrip('@').split('?')[0].rstrip('/').split('/')[-1]
        pk, priv = j.get('target_pk'), j.get('target_private')
        if not pk: pk, priv = known_pk(un)
        if not pk:
            pk, priv = self.lookup_uid(ig, un)
            if not pk: self.log(f'找不到账号 @{un}'); return 0, '找不到账号'
            remember_pk(un, pk, 1 if priv else 0)
        update_job(j['id'], target_pk=str(pk))
        cnt = int(j.get('count') or 0)   # 0 = 全部
        rel = kind; seen = set(); total = 0; mx = None; page = 0; buf = []
        while not self._stop:
            q = f'/api/v1/friendships/{pk}/{rel}/?count=50' + (f'&max_id={mx}' if mx else '') + ('&search_surface=follow_list_page' if rel == 'followers' else '')
            d = self.req(ig, q, f'https://www.instagram.com/{un}/{rel}/')
            if d is None: break
            us, mx = parse_users(d); page += 1
            if page == 1 and is_private_empty(d, priv):
                self.log(f'@{un} 是私密账号，无法获取'); return 0, '私密账号，无法获取'
            new = dedupe(us, seen)
            if cnt: new = new[:max(0, cnt - total)]
            total += len(new); buf += new
            self.log(f'@{un} {"粉丝" if rel=="followers" else "关注"} 第 {page} 页：+{len(new)}，累计 {total}' + (f' / 目标 {cnt}' if cnt else ''))
            for u in new: remember_pk(u['username'], u['pk'], u['is_private'])
            if len(buf) >= 100:   # 边抓边判断边保存，中途停止也不丢
                self._finish(cfg, ig, j, buf, rel); buf = []
            if not mx or (cnt and total >= cnt): break
        if buf: self._finish(cfg, ig, j, buf, rel)
        return total, ''

    def _finish(self, cfg, ig, j, us, rel):
        for u in us:
            u['pic'] = self.avatar(ig, u['pic_url'])
        save_users(j['id'], us, rel)
        if cfg.get('ai_key') and cfg.get('ai_model'):
            self.log(f'AI 判断 {len(us)} 个账号类型…')
            classify(cfg, us, self.log, self.stopped, on_batch=lambda r: set_types(j['id'], r))
        else: self.log('未配置 AI（设置页的接口地址/Key/模型），只保存名单不做类型判断')
        return len(us)
