import json, os, threading
from .paths import data_dir
_lock = threading.Lock()
DEFAULT = {'cookie': '', 'ai_base': 'https://api.openai.com/v1', 'ai_key': '', 'ai_model': '',
           'delay_min': 8.0, 'delay_max': 15.0,
           'fb_cookie': '', 'fb_delay_min': 1.5, 'fb_delay_max': 3.0, 'fb_docs': {},
           'tt_cookie': '', 'tt_ms_token': '', 'tt_device_id': '', 'tt_user_agent': '', 'tt_delay_min': 1.5, 'tt_delay_max': 3.0,
           'port': 8765,
           'ai_fps': 1, 'ai_max_images': '', 'ai_stt_model': '', 'ai_vision': '', 'ai_comment_pages': 5, 'ai_comments_send': 120, 'ai_product': {},
           'ai_stt_provider': '', 'el_key': '', 'el_model': 'scribe_v2', 'el_lang': '', 'skip_version': ''}
def path(): return os.path.join(data_dir(), 'config.json')
def load():
    c = dict(DEFAULT)
    try:
        with open(path(), encoding='utf-8') as f: c.update(json.load(f))
    except Exception: pass
    # v1.1.0 default FB pacing was 4-7s; upgrade only untouched defaults
    if float(c.get('fb_delay_min', 0)) == 4.0 and float(c.get('fb_delay_max', 0)) == 7.0:
        c['fb_delay_min'], c['fb_delay_max'] = 1.5, 3.0
    # v1.7.2：IG 默认节奏 1.5~3 秒太快（容易 429），未改动过的默认值升级为 8~15 秒
    if float(c.get('delay_min', 0)) == 1.5 and float(c.get('delay_max', 0)) == 3.0:
        c['delay_min'], c['delay_max'] = 8.0, 15.0
    for a, b in (('delay_min', 'delay_max'), ('fb_delay_min', 'fb_delay_max'), ('tt_delay_min', 'tt_delay_max')):
        c[a] = max(0.5, float(c[a])); c[b] = max(c[a], float(c[b]))
    return c
def save(upd):
    with _lock:
        c = load(); c.update({k: v for k, v in upd.items() if k in DEFAULT})
        with open(path(), 'w', encoding='utf-8') as f: json.dump(c, f, ensure_ascii=False, indent=2)
        return c
