"""Offline language detection (py3langid, BSD-3) + language -> region hint (inferred from language only)."""
import re
_ID = None
LANGS = {'en': '英语', 'es': '西班牙语', 'pt': '葡萄牙语', 'fr': '法语', 'de': '德语', 'it': '意大利语', 'nl': '荷兰语',
         'ru': '俄语', 'uk': '乌克兰语', 'pl': '波兰语', 'tr': '土耳其语', 'ar': '阿拉伯语', 'fa': '波斯语', 'ur': '乌尔都语',
         'hi': '印地语', 'bn': '孟加拉语', 'id': '印尼语', 'ms': '马来语', 'vi': '越南语', 'th': '泰语', 'zh': '中文',
         'ja': '日语', 'ko': '韩语', 'sw': '斯瓦希里语', 'tl': '菲律宾语', 'ro': '罗马尼亚语', 'el': '希腊语', 'he': '希伯来语',
         'cs': '捷克语', 'hu': '匈牙利语', 'sv': '瑞典语', 'da': '丹麦语', 'no': '挪威语', 'fi': '芬兰语', 'am': '阿姆哈拉语',
         'ne': '尼泊尔语', 'ta': '泰米尔语', 'af': '南非荷兰语', 'az': '阿塞拜疆语', 'kk': '哈萨克语', 'uz': '乌兹别克语'}
REGION = {'en': '英语国家（美/英/印/菲/非洲等）', 'es': '西语国家（墨西哥/西班牙/拉美）', 'pt': '巴西/葡萄牙', 'fr': '法国/西非/北非/加拿大',
          'de': '德国/奥地利/瑞士', 'it': '意大利', 'nl': '荷兰/比利时', 'ru': '俄罗斯/中亚', 'uk': '乌克兰', 'pl': '波兰',
          'tr': '土耳其', 'ar': '中东/北非', 'fa': '伊朗/阿富汗', 'ur': '巴基斯坦/印度', 'hi': '印度', 'bn': '孟加拉/印度',
          'id': '印度尼西亚', 'ms': '马来西亚/文莱', 'vi': '越南', 'th': '泰国', 'zh': '中国/港澳台/新马', 'ja': '日本', 'ko': '韩国',
          'sw': '东非（肯尼亚/坦桑尼亚）', 'tl': '菲律宾', 'ro': '罗马尼亚/摩尔多瓦', 'el': '希腊', 'he': '以色列', 'cs': '捷克',
          'hu': '匈牙利', 'sv': '瑞典', 'da': '丹麦', 'no': '挪威', 'fi': '芬兰', 'am': '埃塞俄比亚', 'ne': '尼泊尔', 'ta': '印度南部/斯里兰卡',
          'af': '南非', 'az': '阿塞拜疆', 'kk': '哈萨克斯坦', 'uz': '乌兹别克斯坦'}
def _ident():
    global _ID
    if _ID is None:
        from py3langid.langid import LanguageIdentifier, MODEL_FILE
        _ID = LanguageIdentifier.from_model_file(MODEL_FILE, norm_probs=True)
        _ID.set_languages(list(LANGS))
    return _ID
_SCRIPTS = [('ko', r'[\uac00-\ud7af]'), ('ja', r'[\u3040-\u30ff]'), ('zh', r'[\u4e00-\u9fff]'), ('th', r'[\u0e00-\u0e7f]'),
            ('hi', r'[\u0900-\u097f]'), ('bn', r'[\u0980-\u09ff]'), ('ar', r'[\u0600-\u06ff]'), ('he', r'[\u0590-\u05ff]'),
            ('el', r'[\u0370-\u03ff]'), ('ru', r'[\u0400-\u04ff]'), ('am', r'[\u1200-\u137f]'), ('ta', r'[\u0b80-\u0bff]')]
def _script(t):
    for code, rx in _SCRIPTS:
        if len(re.findall(rx, t)) >= 2: return code
    return None
_LETTERS = re.compile(r'[^\W\d_]', re.U)
def detect(text):
    """-> (code, 中文名, 地区提示). Short/emoji-only/low-confidence -> unknown."""
    t = re.sub(r'@[\w.]+|https?://\S+|#\w+', ' ', text or '')
    letters = len(_LETTERS.findall(t))
    cjk = len(re.findall(r'[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]', t))
    if letters < 4 and cjk < 2:
        sc = _script(t)
        return (sc, LANGS.get(sc, sc), REGION.get(sc, '')) if sc else ('unknown', '未知', '')
    code, p = _ident().classify(t)
    words = len([w for w in t.split() if _LETTERS.search(w)])
    need = 0.3 if words >= 3 or cjk >= 2 else 0.5 if words == 2 else 0.95
    if p < need:
        sc = _script(t)   # unambiguous scripts still identify very short texts
        if not sc: return 'unknown', '未知', ''
        code = sc
    return code, LANGS.get(code, code), REGION.get(code, '')
