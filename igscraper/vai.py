"""AI 视频分析：抓元数据+评论 → 下载视频 → ffmpeg 抽帧/音频 → 识图模型生成「视频画像」→ 一键复刻脚本。只读，不做任何互动。"""
import base64, datetime, json, math, os, re, shutil, struct, tempfile, time, zlib
import requests
from . import config, db, frames
from .task import Task
from .ig import IG, Blocked
from .matcher import Matcher
from .ctask import detect_platform

def _h(key): return {'Authorization': f'Bearer {key}'}

class AIError(RuntimeError):
    def __init__(self, msg, status=0, body=''): super().__init__(msg); self.status = status; self.body = body
    def __repr__(self): return 'AI 接口错误：' + str(self)

RETRY_SLOW = (408, 502, 503, 504, 520, 522, 524)
def clean_err(status, text):
    t = (text or '').strip()
    if '<html' in t[:500].lower() or '<!doctype' in t[:200].lower():
        m = re.search(r'<title>(.*?)</title>', t, re.S | re.I)
        hint = {524: '接口处理超时（Cloudflare 524，通常是一次发的图太多/太慢）', 504: '网关超时', 502: '网关错误', 522: '连接超时', 520: '上游返回异常'}.get(status, '')
        return f"HTTP {status}{'：' + hint if hint else ''}" + (f"（{re.sub(r'\s+', ' ', m.group(1)).strip()[:80]}）" if m else '')
    try:
        j = json.loads(t); e = j.get('error') or j
        t = e.get('message') if isinstance(e, dict) else str(e)
    except Exception: pass
    return f'HTTP {status}: {str(t)[:300]}'

def _post_chat(base, key, body, stream, timeout):
    url = base.rstrip('/') + '/chat/completions'
    if not stream:
        r = requests.post(url, headers=_h(key), json=body, timeout=timeout)
        if r.status_code != 200: raise AIError(clean_err(r.status_code, r.text), r.status_code, r.text[:2000])
        try: return r.json()['choices'][0]['message']['content'] or ''
        except Exception: raise AIError(f'接口返回格式不对: {r.text[:200]}')
    # 流式：边生成边返回，连接不会因长时间无数据被 Cloudflare 断开（100 秒 524）
    with requests.post(url, headers=_h(key), json=dict(body, stream=True), timeout=(30, timeout), stream=True) as r:
        if r.status_code != 200: raise AIError(clean_err(r.status_code, r.text), r.status_code, r.text[:2000])
        ct = r.headers.get('content-type', '')
        if 'event-stream' not in ct:
            t = r.text
            try: return json.loads(t)['choices'][0]['message']['content'] or ''
            except Exception: raise AIError(f'接口返回格式不对: {t[:200]}')
        out = []
        for line in r.iter_lines(decode_unicode=False):
            if not line: continue
            line = line.decode('utf-8', 'ignore')
            if not line.startswith('data:'): continue
            d = line[5:].strip()
            if d == '[DONE]': break
            try: j = json.loads(d)
            except Exception: continue
            if j.get('error'): raise AIError(clean_err(400, json.dumps(j)), 400, d)
            for ch in j.get('choices') or []:
                c = (ch.get('delta') or {}).get('content') or (ch.get('message') or {}).get('content')
                if c: out.append(c)
        return ''.join(out)

STREAM = {'ok': True}
def chat(base, key, model, content, system=None, max_tokens=None, timeout=900, retries=3):
    msgs = ([{'role': 'system', 'content': system}] if system else []) + [{'role': 'user', 'content': content}]
    body = {'model': model, 'messages': msgs, 'temperature': 0.6}
    if max_tokens: body['max_tokens'] = max_tokens
    for t in range(retries):
        try: return _post_chat(base, key, body, STREAM['ok'], timeout)
        except requests.RequestException as e:
            if t == retries - 1: raise AIError(f'网络错误/超时: {str(e)[:150]}', 524 if isinstance(e, requests.Timeout) else 0)
            time.sleep(5)
        except AIError as e:
            if STREAM['ok'] and e.status in (400, 404, 422) and 'stream' in (e.body or '').lower():
                STREAM['ok'] = False; continue          # 接口不支持流式 → 改普通请求
            if e.status == 429 and t < retries - 1: time.sleep(20 * (t + 1)); continue
            if e.status in (500, 503) and t < retries - 1: time.sleep(10); continue
            raise

def img_part(path_or_bytes, mime='image/jpeg'):
    b = path_or_bytes if isinstance(path_or_bytes, bytes) else open(path_or_bytes, 'rb').read()
    return {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,' + base64.b64encode(b).decode()}}

def test_png(w=256):
    """生成白底红色实心圆 PNG（纯 Python，不依赖 PIL）。"""
    rows = []; c = w / 2; r2 = (w * 0.35) ** 2
    for y in range(w):
        row = bytearray([0])
        for x in range(w): row += b'\xe0\x10\x10' if (x - c) ** 2 + (y - c) ** 2 <= r2 else b'\xff\xff\xff'
        rows.append(bytes(row))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, w, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b'')

def vision_test(base, key, model):
    """-> (ok, 说明)"""
    try:
        ans = chat(base, key, model, [{'type': 'text', 'text': '图片里是什么形状、什么颜色？只用一句中文回答。'}, img_part(test_png(), 'image/png')], max_tokens=100, timeout=120)
    except AIError as e: return False, f'带图请求被拒绝：{e}'
    a = ans.lower()
    ok = ('红' in ans or 'red' in a) and ('圆' in ans or 'circle' in a or 'round' in a)
    return ok, ('✅ 支持识图，模型回答：' if ok else '❌ 模型没认出测试图（红色圆形），可能不支持识图。模型回答：') + ans.strip()[:200]

def transcribe(base, key, model, path):
    with open(path, 'rb') as f:
        r = requests.post(base.rstrip('/') + '/audio/transcriptions', headers=_h(key), files={'file': (os.path.basename(path), f, 'audio/mpeg')},
                          data={'model': model}, timeout=600)
    if r.status_code != 200: raise AIError(f'HTTP {r.status_code}: {r.text[:200]}', r.status_code)
    try: return (r.json().get('text') or '').strip()
    except Exception: return r.text.strip()

def _too_many(e):
    b = (str(e) + ' ' + getattr(e, 'body', '')).lower()
    if getattr(e, 'status', 0) in RETRY_SLOW or '超时' in str(e): return True
    return getattr(e, 'status', 0) in (400, 413, 422) and any(k in b for k in ('image', 'too many', 'too large', 'payload', 'limit', 'maximum', 'exceed', 'context', 'token'))
def _no_vision(e):
    b = (str(e) + ' ' + getattr(e, 'body', '')).lower()
    return getattr(e, 'status', 0) in (400, 404, 415, 422) and any(k in b for k in ('image', 'vision', 'multimodal', 'image_url', 'not support', 'unsupported', 'invalid content'))

SYS = '你是资深短视频操盘手和外贸社媒营销专家，擅长拆解 TikTok / Instagram Reels / Facebook 爆款视频。全部用简体中文回答，结构清晰，用 Markdown。'
PROFILE_SPEC = """请输出「视频画像」，Markdown 格式，必须包含以下二级标题（## 开头）。
硬性要求：
- 必须基于上面给出的真实画面和评论，禁止空话套话（如“画面精美”“吸引眼球”“节奏紧凑”这种不带细节的话不要写）。
- 画面相关的每个判断都要标注时间点（如 0.25s、4s），并写出看到的具体东西：人物/手部动作、产品是什么样、背景场景、屏幕上的文字原文、转场方式。
- 评论相关的判断要引用评论原话（保留原语言，后面括号附中文意思），并给出大致数量或占比。
- 画面里看不清或没有的信息，直接写“画面中未体现”，不要编造。
## 一、前 3 秒钩子（逐个时间点描述 0~3s 的画面，说明到底靠什么留住人）
## 二、结构与节奏（表格：时间段 | 画面内容 | 屏幕文字/口播 | 作用）
## 三、视觉风格（景别、运镜、光线、色调、字幕/贴纸样式、剪辑频率：平均几秒一个镜头）
## 四、核心卖点（画面/文案里实际展示了哪些卖点，分别在第几秒）
## 五、目标人群（结合评论者的提问内容和语言推断：B 端买家/批发商/C 端消费者，哪些国家地区）
## 六、情绪触发点
## 七、评论区的问题与顾虑（按类别归纳，每类给：数量/占比、2~3 条原话、视频里有没有回答）
## 八、为什么能成为爆款（3~6 条，每条都要对应上面的具体证据）
## 九、可复用的爆款公式（一句话概括 + 可直接套用的模板）"""

def meta_text(M, comments, transcript):
    tags = ' '.join('#' + t for t in M.get('tags') or [])
    s = [f"平台：{M.get('platform')}", f"账号：{M.get('account')}", f"链接：{M.get('url')}", f"发布日期：{M.get('date') or '未知'}",
         f"时长：{M.get('duration', 0):.1f} 秒", f"播放：{M.get('plays') or '未知'}　点赞：{M.get('likes') or '未知'}　评论：{M.get('comments') or '未知'}　分享：{M.get('shares') if M.get('shares') is not None else '未知'}",
         f"文案：{M.get('caption') or '(无)'}", f"标签：{tags or '(无)'}"]
    if transcript: s.append(f"口播/音频转写：{transcript[:6000]}")
    if comments:
        s.append(f"评论（共抓取 {len(comments)} 条，提问/询盘类在前，[问]=提问类）：")
        s += [f"- {'[问] ' if c.get('q') else ''}{c['user']}: {c['text'][:300]}" + (f"（赞 {c['likes']}）" if c.get('likes') else '') for c in comments]
    return '\n'.join(s)

def replicate_prompt(profile, product, M):
    qs = '\n'.join(f"- {c['user']}: {c['text'][:200]}" for c in (M.get('top_comments') or [])[:30])
    return f"""下面是一条爆款视频的「视频画像」（平台：{M.get('platform')}，原时长约 {M.get('duration', 0):.0f} 秒，播放 {M.get('plays') or '未知'}）：

{profile}

原视频评论区的高频提问（原话）：
{qs or '(无)'}

我的产品/需求信息：
{product or '(未填写，请按同类产品通用写法，并在需要我替换的地方用【】标出)'}

请基于这个画像为我的产品「一键复刻」一条新视频。要求：
1. 复刻的是结构、节奏、钩子思路和情绪设计；文案、台词、画面必须全部原创，不得照抄原视频的原话、字幕或标志性画面。
2. 总时长与原视频接近；分镜数量与节奏参照画像里的「结构与节奏」，每个镜头在备注里写明对应原视频的哪一段（如“对应原 0~3s 钩子”）。
3. 前 3 秒要有同等强度的钩子，写清楚具体拍什么、怎么动、屏幕上打什么字。
4. 把上面评论区最常见的 3~5 个问题（价格、起订量、定制、发货等）提前在视频画面/字幕或文案里回答或引导私信，不要编造我没给的具体数字，用【】留空。
5. 拍摄要求要具体到普通工厂/个人能执行（机位、景别、道具、手部动作），不要写空泛的形容词。
输出 Markdown，包含以下二级标题：
## 一、分镜脚本（表格：镜号 | 时长 | 画面/拍摄方式 | 口播/字幕（目标平台语言 + 中文） | 备注/对应原视频）
## 二、发布文案（2 个版本，按目标平台常用语言写，附中文翻译）
## 三、话题标签（15~25 个，分热门/精准/长尾三组）
## 四、封面与标题建议（3 个方案，写清封面画面和封面大字）
## 五、发布建议（发布时间、置顶评论、评论区常见问题的回复话术、注意事项）"""

# ---------------- 抓取 ----------------
def _num(x):
    try: return int(x)
    except Exception: return None
def _tags(cap): return re.findall(r'#([^\s#]+)', cap or '')

def make_client(pl, cfg, log, stopf):
    if pl == 'instagram':
        if not cfg.get('cookie'): raise Blocked('缺少 Instagram Cookie')
        return IG(cfg['cookie'], float(cfg['delay_min']), float(cfg['delay_max']), log, stopf)
    if pl == 'facebook':
        if not cfg.get('fb_cookie'): raise Blocked('缺少 Facebook Cookie')
        from .fb import FB
        c = FB(cfg['fb_cookie'], float(cfg['fb_delay_min']), float(cfg['fb_delay_max']), log, stopf,
               on_cookie=lambda ck: config.save({'fb_cookie': ck}), docs=cfg.get('fb_docs') or None)
        c.login(); return c
    if not cfg.get('tt_cookie'): raise Blocked('缺少 TikTok Cookie')
    from .tt import TT, parse_session
    return TT(parse_session(cfg['tt_cookie'], cfg.get('tt_ms_token'), cfg.get('tt_device_id'), cfg.get('tt_user_agent')),
              float(cfg['tt_delay_min']), float(cfg['tt_delay_max']), log, stopf)

def fetch_meta(pl, c, url, row=None):
    """-> (meta dict, video_url, download fn(url, path))"""
    row = row or {}
    if pl == 'tiktok':
        it0 = c.resolve(url); u = it0['url']
        r = c._http(u, 'https://www.tiktok.com/')
        m = re.search(r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', r.text, re.S)
        if not m: raise RuntimeError('TikTok 视频页没有数据（可能被风控或链接无效）')
        sc = json.loads(m.group(1)).get('__DEFAULT_SCOPE__', {}).get('webapp.video-detail', {})
        it = (sc.get('itemInfo') or {}).get('itemStruct')
        if not it: raise RuntimeError(f"TikTok 视频页没有视频信息（statusCode={sc.get('statusCode')}）")
        st = it.get('stats') or {}; v = it.get('video') or {}; ct = _num(it.get('createTime')) or 0
        M = dict(platform='tiktok', url=u, shortcode=str(it['id']), account=(it.get('author') or {}).get('uniqueId', it0['account']),
                 caption=it.get('desc') or '', tags=[x.get('title') for x in it.get('challenges') or [] if x.get('title')] or _tags(it.get('desc')),
                 plays=_num(st.get('playCount')), likes=_num(st.get('diggCount')), comments=_num(st.get('commentCount')), shares=_num(st.get('shareCount')),
                 date=datetime.datetime.fromtimestamp(ct).strftime('%Y-%m-%d') if ct else '', duration=float(v.get('duration') or 0),
                 owner_id=(it.get('author') or {}).get('id', ''))
        vurl = v.get('playAddr') or v.get('downloadAddr')
        def dl(vu, path):
            H = dict(c.H, Referer='https://www.tiktok.com/'); H.pop('Accept', None)
            r = c.creq.get(vu, headers=H, impersonate='chrome', proxies=c.proxies, timeout=300, stream=True)
            if r.status_code not in (200, 206): raise RuntimeError(f'视频下载失败 HTTP {r.status_code}')
            with open(path, 'wb') as f:
                for ch in r.iter_content(): f.write(ch)
        return M, vurl, dl
    if pl == 'instagram':
        code = (re.search(r'/(?:p|reel|reels|tv)/([\w-]+)', url) or [None, None])[1]
        if not code: raise RuntimeError(f'无法识别 IG 链接：{url}')
        d = c.get(f'/api/v1/media/{IG.pk_of(code)}/info/', pace=False)
        its = (d or {}).get('items') or []
        if not its: raise RuntimeError('Instagram 没有返回这条内容的信息')
        it = its[0]; cap = ((it.get('caption') or {}).get('text') or '')
        vv = it.get('video_versions') or []
        if not vv and it.get('carousel_media'):
            vv = next((x.get('video_versions') for x in it['carousel_media'] if x.get('video_versions')), [])
        ta = it.get('taken_at') or 0
        M = dict(platform='instagram', url=f'https://www.instagram.com/reel/{code}/', shortcode=code, account=(it.get('user') or {}).get('username', ''),
                 caption=cap, tags=_tags(cap), plays=_num(it.get('play_count') or it.get('ig_play_count') or it.get('view_count')), likes=_num(it.get('like_count')),
                 comments=_num(it.get('comment_count')), shares=None, date=datetime.datetime.fromtimestamp(ta).strftime('%Y-%m-%d') if ta else '',
                 duration=float(it.get('video_duration') or 0))
        def dl(vu, path):
            r = requests.get(vu, headers={'User-Agent': c.s.headers['User-Agent'], 'Referer': 'https://www.instagram.com/'}, timeout=300, stream=True)
            if r.status_code != 200: raise RuntimeError(f'视频下载失败 HTTP {r.status_code}')
            with open(path, 'wb') as f:
                for ch in r.iter_content(65536): f.write(ch)
        return M, (vv[0]['url'] if vv else None), dl
    # facebook
    it = c.resolve(url)
    r = c.nav(it['url'], 'https://www.facebook.com/'); t = r.text if r else ''
    js = lambda p: (lambda m: json.loads('"' + m.group(1) + '"') if m else None)(re.search(p, t))
    vurl = (js(r'"browser_native_hd_url":"((?:[^"\\]|\\.)+)"') or js(r'"playable_url_quality_hd":"((?:[^"\\]|\\.)+)"') or
            js(r'"browser_native_sd_url":"((?:[^"\\]|\\.)+)"') or js(r'"playable_url":"((?:[^"\\]|\\.)+)"'))
    cap = js(r'"message":\{(?:"delight_ranges":\[\],)?(?:"[a-z_]+":[^{}]*?,)*?"text":"((?:[^"\\]|\\.)*)"') or row.get('caption') or ''
    pc = re.search(r'"play_count":(\d+)', t) or re.search(r'"video_view_count":(\d+)', t)
    M = dict(platform='facebook', url=it['url'], shortcode=it['shortcode'], account=it.get('account') or row.get('account', ''), caption=cap, tags=_tags(cap),
             plays=int(pc.group(1)) if pc else row.get('plays'), likes=row.get('likes'), comments=row.get('comment_count'), shares=row.get('shares'),
             date=row.get('publish_date', ''), duration=0.0, _item=it)
    def dl(vu, path):
        r = c.s.get(vu, timeout=300, stream=True, headers={'Referer': 'https://www.facebook.com/'})
        if r.status_code != 200: raise RuntimeError(f'视频下载失败 HTTP {r.status_code}')
        with open(path, 'wb') as f:
            for ch in r.iter_content(65536): f.write(ch)
    return M, vurl, dl

def fetch_comments(pl, c, M, pages, max_c):
    if pl == 'instagram': cs, _ = c.comments_full(M['shortcode'], pages, max_c, False)
    elif pl == 'facebook': cs = c.gql_comments(M['_item'], pages, M['url'])[:max_c]
    else: cs = c.comments_full({'shortcode': M['shortcode'], 'url': M['url'], 'account': M['account']}, pages, max_c, False)
    m = Matcher((), True, True); out = []
    for x in cs:
        if not x.get('text') or x.get('is_reply'): continue
        out.append({'user': x.get('user', ''), 'text': x['text'], 'likes': int(x.get('likes') or 0), 'q': m.is_q(x['text'], x.get('user'), M['account'])})
    out.sort(key=lambda x: (not x['q'], -x['likes']))
    return out

# ---------------- 任务 ----------------
BATCH = {}   # 本次运行中 (接口, 模型) 成功过的每批图片数，后续直接用
class AnalyzeTask(Task):
    def _crawl(self, cfg, P, rid):
        b, k, model = cfg['ai_base'], cfg['ai_key'], cfg['ai_model']
        if not (b and k and model): raise RuntimeError('请先在「AI 设置」里填写接口地址、Key 并选择模型')
        url = (P.get('url') or '').strip(); row = None
        if P.get('key'):
            rs = db.get_videos([P['key']]); row = rs[0] if rs else None
            if row: url = row['url']
        pl = detect_platform(url or '')
        if not pl: raise RuntimeError('无法识别链接（支持 TikTok / Instagram / Facebook）')
        fps = float(cfg.get('ai_fps') or 1); cap = int(cfg.get('ai_max_images') or 0)
        cpages, cmax, csend = int(cfg.get('ai_comment_pages') or 5), 300, int(cfg.get('ai_comments_send') or 120)
        tmp = tempfile.mkdtemp(prefix='igs_ai_'); self.set(target=6, current=url, tmp=tmp)
        stopf = lambda: self._stop
        try:
            self.set(stage='① 读取视频信息', scanned=0)
            c = make_client(pl, cfg, self.log, stopf)
            M, vurl, dl = fetch_meta(pl, c, url, row)
            self.log(f"[{M['platform']}] @{M['account']} 文案：{M['caption'][:60]}")
            self.set(stage='② 抓取评论', scanned=1)
            try: cs = fetch_comments(pl, c, M, cpages, cmax)
            except Exception as e: cs = []; self.log(f'⚠️ 评论抓取失败，跳过：{e}')
            nq = sum(x['q'] for x in cs); self.log(f'评论 {len(cs)} 条，其中提问/询盘 {nq} 条（发给 AI 前 {min(len(cs), csend)} 条）')
            cs = cs[:csend]
            if self._stop: return
            self.set(stage='③ 下载视频', scanned=2); fr = []; transcript = ''; vpath = os.path.join(tmp, 'video.mp4')
            if not vurl: self.log('⚠️ 没拿到视频地址（可能是图片帖），只用文案和评论分析')
            else:
                dl(vurl, vpath); self.log(f'视频已下载 {os.path.getsize(vpath)/1e6:.1f} MB（临时文件，分析完自动删除）')
                self.set(stage='④ 抽帧 / 提取音频', scanned=3)
                dur, has_a = frames.probe(vpath); M['duration'] = dur or M.get('duration') or 0
                sc = frames.scene_times(vpath)
                ts = frames.frame_schedule(M['duration'], fps=fps, scene_times=sc)
                fr = frames.extract_frames(vpath, tmp, ts)
                self.log(f"时长 {M['duration']:.1f}s，前 3 秒每秒 4 张、之后每秒 {fps:g} 张，另加转场帧 {len(ts) - len(frames.frame_schedule(M['duration'], fps=fps))} 张，共截图 {len(fr)} 张")
                stt = (cfg.get('ai_stt_model') or '').strip()
                if stt and has_a:
                    try:
                        ap = frames.extract_audio(vpath, os.path.join(tmp, 'audio.mp3'))
                        if ap: transcript = transcribe(b, k, stt, ap); self.log(f'口播转写 {len(transcript)} 字')
                    except Exception as e: self.log(f'⚠️ 语音转写不可用，已跳过：{e}')
                elif not stt: self.log('未设置语音转写模型，跳过口播转写（可在 AI 设置里填写，如 whisper-1）')
            if self._stop: return
            self.set(stage='⑤ AI 分析中（可能需要几分钟）', scanned=4)
            profile, vision, note = self.ai_profile(b, k, model, M, cs, transcript, fr, cap, cfg.get('ai_vision', ''))
            M.pop('_item', None)
            aid = db.save_analysis({'platform': pl, 'url': M['url'], 'account': M['account'], 'caption': M['caption'], 'meta': json.dumps(dict(M, frames=len(fr), comment_n=len(cs), question_n=nq, top_comments=[c for c in cs if c['q']][:30]), ensure_ascii=False),
                                    'profile': profile, 'vision': int(vision), 'frames': len(fr), 'transcript': transcript, 'note': note,
                                    'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
            self.set(stage='完成', scanned=6, result_id=aid, matched=1); self.log(f'✅ 视频画像已生成并保存（#{aid}）{note}')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            self.log('已删除本地临时视频和截图' if not os.path.exists(tmp) else f'⚠️ 临时目录未能删除：{tmp}')

    def ai_profile(self, b, k, model, M, cs, transcript, fr, cap, vmode):
        text = meta_text(M, cs, transcript)
        def text_only(why):
            self.log(f'⚠️ {why}，改为仅根据文案/标签/评论分析')
            return chat(b, k, model, text + '\n\n（注意：本次没有画面信息，画面相关部分请根据文案合理推断并注明“推断”）\n\n' + PROFILE_SPEC, SYS), False, f'（{why}，本次为纯文字分析）'
        if not fr: return chat(b, k, model, text + '\n\n' + PROFILE_SPEC, SYS), False, '（无画面，纯文字分析）'
        if vmode == '0': return text_only('设置里已关闭识图')
        def parts(sub, intro):
            p = [{'type': 'text', 'text': intro}]
            for t, path in sub: p += [{'type': 'text', 'text': f'[{t:.2f}s]'}, img_part(path)]
            return p
        bk = (b, model); size = cap if cap > 0 else min(len(fr), BATCH.get(bk, len(fr)))
        while True:
            batches = [fr[i:i + size] for i in range(0, len(fr), size)]
            try:
                if len(batches) == 1:
                    self.log(f'发送 {len(fr)} 张截图给 AI（一次请求）')
                    t0 = time.time()
                    out = chat(b, k, model, parts(fr, f'下面是视频按时间顺序截取的全部 {len(fr)} 张画面，每张前标了时间点。\n\n{text}\n\n') + [{'type': 'text', 'text': PROFILE_SPEC}], SYS)
                    self.log(f'AI 返回，用时 {time.time()-t0:.0f}s'); return out, True, ''
                self.log(f'共 {len(fr)} 张截图，分 {len(batches)} 批（每批最多 {size} 张）依次发送，最后汇总，不丢帧')
                notes = []
                for i, bt in enumerate(batches, 1):
                    if self._stop: raise RuntimeError('已停止')
                    self.set(stage=f'⑤ AI 看图 第 {i}/{len(batches)} 批')
                    intro = (f'这是一条短视频的第 {i}/{len(batches)} 批画面（{bt[0][0]:.1f}s ~ {bt[-1][0]:.1f}s，共 {len(bt)} 张，每张前标了时间点）。视频文案：{M.get("caption","")[:300]}\n'
                             '请逐个时间点详细描述：画面内容、人物动作、产品展示方式、景别/运镜、屏幕文字/字幕原文、转场。只描述，不要总结。')
                    t0 = time.time()
                    notes.append(f'### 第 {i} 批 {bt[0][0]:.1f}s~{bt[-1][0]:.1f}s\n' + chat(b, k, model, parts(bt, intro), SYS))
                    self.log(f'  第 {i} 批 {len(bt)} 张完成，用时 {time.time()-t0:.0f}s')
                BATCH[bk] = size
                self.set(stage='⑤ AI 汇总生成视频画像')
                out = chat(b, k, model, f'以下是对整条视频全部画面的逐时间点描述（分批看图得到）：\n\n' + '\n\n'.join(notes) + f'\n\n{text}\n\n{PROFILE_SPEC}', SYS)
                return out, True, f'（{len(fr)} 张截图分 {len(batches)} 批发送后汇总）'
            except AIError as e:
                if _too_many(e) and size > 1:
                    size = max(1, math.ceil(size / 2)); self.log(f'接口拒绝或超时（{str(e)[:120]}），自动改为每批 {size} 张重试（不丢帧）'); continue
                if vmode != '1' and _no_vision(e): return text_only(f'模型不支持识图（{str(e)[:120]}）')
                raise

def replicate(aid, product):
    a = db.get_analysis(aid)
    if not a: raise RuntimeError('分析记录不存在')
    cfg = config.load()
    if not (cfg['ai_base'] and cfg['ai_key'] and cfg['ai_model']): raise RuntimeError('请先在「AI 设置」里填写接口并选择模型')
    out = chat(cfg['ai_base'], cfg['ai_key'], cfg['ai_model'], replicate_prompt(a['profile'], product, json.loads(a['meta'] or '{}')), SYS)
    db.update_analysis(aid, product=product, replica=out); return out

def to_markdown(a):
    M = json.loads(a['meta'] or '{}')
    s = [f"# AI 视频分析 #{a['id']}", '', f"- 平台：{a['platform']}", f"- 账号：@{a['account']}", f"- 链接：{a['url']}", f"- 发布日期：{M.get('date') or '未知'}",
         f"- 播放 {M.get('plays') or '-'} · 点赞 {M.get('likes') or '-'} · 评论 {M.get('comments') or '-'} · 分享 {M.get('shares') if M.get('shares') is not None else '-'}",
         f"- 时长 {M.get('duration', 0):.1f}s · 截图 {a['frames']} 张 · {'识图分析' if a['vision'] else '纯文字分析'} · 分析时间 {a['created_at']}",
         f"- 文案：{a['caption']}", '', '---', '', '# 视频画像', '', a['profile'] or '']
    if a.get('replica'): s += ['', '---', '', '# 一键复刻', '', f"**我的产品信息：** {a.get('product') or ''}", '', a['replica']]
    if a.get('transcript'): s += ['', '---', '', '## 附：口播转写', '', a['transcript']]
    return '\n'.join(s)
