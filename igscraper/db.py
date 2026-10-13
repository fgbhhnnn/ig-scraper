import sqlite3, os, threading
from .paths import data_dir
_lock = threading.Lock()
COLS = ['platform','shortcode','content_type','account','url','caption','plays','likes','comment_count','question_count',
        'sample_questions','publish_date','source','media_id','scanned_comments','crawled_at','run_id','shares']
def conn():
    c = sqlite3.connect(os.path.join(data_dir(), 'results.db'), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c
def _cols(c, t): return [r[1] for r in c.execute(f'PRAGMA table_info({t})')]
def init():
    _init_main(); init_comments(); init_analyses()
def _init_main():
    with _lock, conn() as c:
        # v1.0 schema had no platform column -> migrate (all old rows are Instagram videos)
        if _cols(c, 'videos') and 'platform' not in _cols(c, 'videos'):
            c.execute('ALTER TABLE videos RENAME TO videos_v1')
        if _cols(c, 'seen') and 'platform' not in _cols(c, 'seen'):
            c.execute('ALTER TABLE seen RENAME TO seen_v1')
        c.execute('''CREATE TABLE IF NOT EXISTS videos(platform TEXT NOT NULL DEFAULT 'instagram', shortcode TEXT NOT NULL,
          content_type TEXT DEFAULT 'video', account TEXT, url TEXT, caption TEXT, plays INTEGER, likes INTEGER, comment_count INTEGER,
          question_count INTEGER, sample_questions TEXT, publish_date TEXT, source TEXT, media_id TEXT, scanned_comments INTEGER,
          crawled_at TEXT, run_id TEXT, PRIMARY KEY(platform, shortcode))''')
        c.execute('''CREATE TABLE IF NOT EXISTS seen(platform TEXT NOT NULL DEFAULT 'instagram', shortcode TEXT NOT NULL,
          question_count INTEGER, seen_at TEXT, PRIMARY KEY(platform, shortcode))''')
        if 'shares' not in _cols(c, 'videos'): c.execute('ALTER TABLE videos ADD COLUMN shares INTEGER')
        if _cols(c, 'videos_v1'):
            old = [k for k in COLS if k in _cols(c, 'videos_v1')]
            c.execute(f"INSERT OR IGNORE INTO videos(platform,content_type,{','.join(old)}) SELECT 'instagram','video',{','.join(old)} FROM videos_v1")
            c.execute('DROP TABLE videos_v1')
        if _cols(c, 'seen_v1'):
            c.execute("INSERT OR IGNORE INTO seen SELECT 'instagram',shortcode,question_count,seen_at FROM seen_v1"); c.execute('DROP TABLE seen_v1')
def seen_codes(platform):
    with conn() as c: return {r[0] for r in c.execute('SELECT shortcode FROM seen WHERE platform=?', (platform,))}
def mark_seen(platform, code, q, ts):
    with _lock, conn() as c: c.execute('INSERT OR REPLACE INTO seen VALUES(?,?,?,?)', (platform, code, q, ts))
def upsert(v):
    with _lock, conn() as c:
        c.execute(f"INSERT OR REPLACE INTO videos({','.join(COLS)}) VALUES({','.join('?'*len(COLS))})", [v.get(k) for k in COLS])
def rows(q='', run_id=None, platform=None, content_type=None):
    sql, a = 'SELECT * FROM videos WHERE 1=1', []
    if q:
        sql += ' AND (account LIKE ? OR caption LIKE ? OR sample_questions LIKE ? OR source LIKE ?)'; a += [f'%{q}%']*4
    if run_id: sql += ' AND run_id=?'; a.append(run_id)
    if platform: sql += ' AND platform=?'; a.append(platform)
    if content_type: sql += ' AND content_type=?'; a.append(content_type)
    sql += ' ORDER BY question_count DESC, plays DESC'
    with conn() as c: return [dict(r) for r in c.execute(sql, a)]
def clear():
    with _lock, conn() as c: c.execute('DELETE FROM videos'); c.execute('DELETE FROM seen')

CCOLS = ['platform','comment_id','post_id','post_url','account','commenter','text','lang','lang_name','region','likes',
         'ctime','is_reply','is_author','is_spam','matched','crawled_at','run_id']
def init_comments():
    with _lock, conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS comments(platform TEXT NOT NULL, comment_id TEXT NOT NULL, post_id TEXT, post_url TEXT,
          account TEXT, commenter TEXT, text TEXT, lang TEXT, lang_name TEXT, region TEXT, likes INTEGER, ctime TEXT, is_reply INTEGER,
          is_author INTEGER, is_spam INTEGER, matched INTEGER, crawled_at TEXT, run_id TEXT, PRIMARY KEY(platform, comment_id))''')
def upsert_comments(rows):
    with _lock, conn() as c:
        c.executemany(f"INSERT OR REPLACE INTO comments({','.join(CCOLS)}) VALUES({','.join('?'*len(CCOLS))})",
                      [[r.get(k) for k in CCOLS] for r in rows])
def comment_rows(platform=None, run_id=None, post_url=None):
    sql, a = 'SELECT * FROM comments WHERE 1=1', []
    if platform: sql += ' AND platform=?'; a.append(platform)
    if run_id: sql += ' AND run_id=?'; a.append(run_id)
    if post_url: sql += ' AND post_url=?'; a.append(post_url)
    sql += ' ORDER BY crawled_at DESC, likes DESC'
    with conn() as c: return [dict(r) for r in c.execute(sql, a)]
def get_videos(keys):
    """keys: list of 'platform|shortcode'"""
    out = []
    with conn() as c:
        for k in keys:
            p, _, s = k.partition('|')
            r = c.execute('SELECT * FROM videos WHERE platform=? AND shortcode=?', (p, s)).fetchone()
            if r: out.append(dict(r))
    return out
def clear_comments():
    with _lock, conn() as c: c.execute('DELETE FROM comments')

ACOLS = ['platform', 'url', 'account', 'caption', 'meta', 'profile', 'vision', 'frames', 'transcript', 'note', 'created_at']
def init_analyses():
    with _lock, conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, url TEXT, account TEXT, caption TEXT,
          meta TEXT, profile TEXT, vision INTEGER, frames INTEGER, transcript TEXT, note TEXT, created_at TEXT, product TEXT, replica TEXT)''')
        if 'replicas' not in _cols(c, 'analyses'): c.execute('ALTER TABLE analyses ADD COLUMN replicas TEXT')
def save_analysis(a):
    init_analyses()
    with _lock, conn() as c:
        return c.execute(f"INSERT INTO analyses({','.join(ACOLS)}) VALUES({','.join('?'*len(ACOLS))})", [a.get(k) for k in ACOLS]).lastrowid
def update_analysis(aid, **kw):
    with _lock, conn() as c: c.execute(f"UPDATE analyses SET {','.join(k + '=?' for k in kw)} WHERE id=?", list(kw.values()) + [aid])
def get_analysis(aid):
    init_analyses()
    with conn() as c:
        r = c.execute('SELECT * FROM analyses WHERE id=?', (aid,)).fetchone(); return dict(r) if r else None
def list_analyses():
    init_analyses()
    import json
    out = []
    with conn() as c:
        for r in c.execute('SELECT id,platform,url,account,caption,vision,frames,created_at,replica IS NOT NULL AS has_replica,meta FROM analyses ORDER BY id DESC'):
            d = dict(r)
            try: d['thumb'] = json.loads(d.pop('meta') or '{}').get('thumb', '')
            except Exception: d['thumb'] = ''
            out.append(d)
    return out
def delete_analysis(aid):
    with _lock, conn() as c: c.execute('DELETE FROM analyses WHERE id=?', (aid,))
def add_replica(aid, product, text, product_json=''):
    import json, datetime
    a = get_analysis(aid); vs = json.loads(a.get('replicas') or '[]')
    if not vs and a.get('replica'): vs.append({'at': a.get('created_at', ''), 'product': a.get('product') or '', 'text': a['replica']})
    vs.append({'at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'product': product, 'text': text, 'product_json': product_json})
    update_analysis(aid, product=product, replica=text, replicas=json.dumps(vs, ensure_ascii=False))
