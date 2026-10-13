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
    _init_main(); init_comments()
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
