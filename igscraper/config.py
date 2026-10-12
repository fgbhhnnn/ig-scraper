import json, os, threading
from .paths import data_dir
_lock = threading.Lock()
DEFAULT = {'cookie': '', 'ai_base': 'https://api.openai.com/v1', 'ai_key': '', 'ai_model': '',
           'delay_min': 1.5, 'delay_max': 3.0}
def path(): return os.path.join(data_dir(), 'config.json')
def load():
    c = dict(DEFAULT)
    try:
        with open(path(), encoding='utf-8') as f: c.update(json.load(f))
    except Exception: pass
    return c
def save(upd):
    with _lock:
        c = load(); c.update({k: v for k, v in upd.items() if k in DEFAULT})
        with open(path(), 'w', encoding='utf-8') as f: json.dump(c, f, ensure_ascii=False, indent=2)
        return c
