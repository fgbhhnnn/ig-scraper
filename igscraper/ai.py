import json, re, requests
def _h(key): return {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
def list_models(base, key):
    r = requests.get(base.rstrip('/') + '/models', headers=_h(key), timeout=20)
    if r.status_code != 200: raise RuntimeError(f'HTTP {r.status_code}: {r.text[:200]}')
    try: d = r.json()
    except Exception: raise RuntimeError('返回的不是 JSON，请检查 Base 地址（通常以 /v1 结尾）')
    items = d.get('data', d if isinstance(d, list) else [])
    return sorted({(m.get('id') if isinstance(m, dict) else str(m)) for m in items if m})
PROMPT = """你是外贸获客助手。用户想在 Instagram 上找同行(竞品)视频，评论区里有买家询盘的视频才有价值。
行业/种子关键词: {kws}
种子话题标签: {tags}
评论区关键信息(用户关心的询盘类型): {info}
请输出 JSON(不要多余文字):
{{"keywords": [15个左右英文为主的 Instagram 搜索词, 可含少量西语/法语/阿语/印地语常用词],
 "hashtags": [15个左右相关标签, 不带#],
 "comment_phrases": [40个左右评论区询盘短语, 多语言: 英语/西语/葡语/法语/阿语/俄语/印地语(拉丁转写)/中文, 如 "how much", "price?", "moq", "precio", "cuánto", "wholesale price", "dm price", "catalog", "多少钱"]}}"""
def expand(base, key, model, kws, tags, info):
    body = {'model': model, 'temperature': 0.7,
            'messages': [{'role': 'user', 'content': PROMPT.format(kws=', '.join(kws) or '无', tags=', '.join(tags) or '无', info=', '.join(info) or '价格, MOQ, 怎么买')}]}
    r = requests.post(base.rstrip('/') + '/chat/completions', headers=_h(key), json=body, timeout=120)
    if r.status_code != 200: raise RuntimeError(f'HTTP {r.status_code}: {r.text[:200]}')
    txt = r.json()['choices'][0]['message']['content']
    m = re.search(r'\{.*\}', txt, re.S)
    if not m: raise RuntimeError('模型没有返回 JSON')
    d = json.loads(m.group(0))
    cl = lambda xs: [str(x).strip() for x in (xs or []) if str(x).strip()]
    return {'keywords': cl(d.get('keywords')), 'hashtags': [t.lstrip('#') for t in cl(d.get('hashtags'))], 'comment_phrases': cl(d.get('comment_phrases'))}
