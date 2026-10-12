import sqlite3, os, threading, json
from .paths import data_dir
_lock = threading.Lock()
COLS = ['shortcode','account','url','caption','plays','likes','comment_count','question_count',
        'sample_questions','publish_date','source','media_id','scanned_comments','crawled_at','run_id']
def conn():
    c = sqlite3.connect(os.path.join(data_dir(), 'results.db'), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c
def init():
    with _lock, conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS videos(shortcode TEXT PRIMARY KEY, account TEXT, url TEXT, caption TEXT,
          plays INTEGER, likes INTEGER, comment_count INTEGER, question_count INTEGER, sample_questions TEXT,
          publish_date TEXT, source TEXT, media_id TEXT, scanned_comments INTEGER, crawled_at TEXT, run_id TEXT)''')
        # every scanned shortcode (incl. no-question ones) so "skip existing" works
        c.execute('CREATE TABLE IF NOT EXISTS seen(shortcode TEXT PRIMARY KEY, question_count INTEGER, seen_at TEXT)')
def seen_codes():
    with conn() as c: return {r[0] for r in c.execute('SELECT shortcode FROM seen')}
def mark_seen(code, q, ts):
    with _lock, conn() as c: c.execute('INSERT OR REPLACE INTO seen VALUES(?,?,?)', (code, q, ts))
def upsert(v):
    with _lock, conn() as c:
        c.execute(f"INSERT OR REPLACE INTO videos({','.join(COLS)}) VALUES({','.join('?'*len(COLS))})",
                  [v.get(k) for k in COLS])
def rows(q='', run_id=None):
    sql, a = 'SELECT * FROM videos WHERE 1=1', []
    if q:
        sql += ' AND (account LIKE ? OR caption LIKE ? OR sample_questions LIKE ? OR source LIKE ?)'; a += [f'%{q}%']*4
    if run_id: sql += ' AND run_id=?'; a.append(run_id)
    sql += ' ORDER BY question_count DESC, plays DESC'
    with conn() as c: return [dict(r) for r in c.execute(sql, a)]
def clear():
    with _lock, conn() as c: c.execute('DELETE FROM videos'); c.execute('DELETE FROM seen')
