"""Comment filter expressions.
  price and moq | (price or "how much") and not scam | lang:es && price | likes>5 | user:abc | is_reply:0
Operators: and/&&/&/并且/且 ; or/||/|/或者/或 ; not/!/-/不含/非 ; parentheses; adjacent terms = AND.
"""
import re
class FilterError(ValueError): pass
AND, OR, NOT = {'and', '&&', '&', '并且', '且'}, {'or', '||', '|', '或者', '或'}, {'not', '!', '不含', '非'}
_TOK = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*"|“[^”]*”|\'[^\']*\')|([A-Za-z_]+(?:>=|<=|!=|>|<|=|:)[^\s()&|"“\']+)|(&&|\|\||[&|!])|(并且|或者|不含)|((?:(?!并且|或者|不含)[^\s()&|!"“\'])+))')

def tokenize(s):
    out, i = [], 0
    s = s.strip()
    while i < len(s):
        m = _TOK.match(s, i)
        if not m or m.end() == i:
            if s[i:].strip() == '': break
            raise FilterError(f'无法识别的字符：{s[i]}（位置 {i+1}）')
        i = m.end()
        lp, rp, q, fld, sym, zh, w = m.groups()
        if fld: out.append(('TERM', fld)); continue
        if lp: out.append(('(', '('))
        elif rp: out.append((')', ')'))
        elif q: out.append(('TERM', q[1:-1].replace('\\"', '"')))
        elif sym or zh: out.append(('OP', sym or zh))
        elif w is not None:
            lw = w.lower()
            if lw in AND | OR | NOT: out.append(('OP', lw))
            elif w.startswith('-') and len(w) > 1: out += [('OP', 'not'), ('TERM', w[1:])]
            else: out.append(('TERM', w))
    return out

def parse(s):
    """-> AST tuples: ('and',a,b) ('or',a,b) ('not',a) ('term',str) ('field',name,op,val) ; None for empty."""
    toks = tokenize(s or ''); pos = [0]
    if not toks: return None
    peek = lambda: toks[pos[0]] if pos[0] < len(toks) else (None, None)
    def nxt(): t = peek(); pos[0] += 1; return t
    def is_op(t, group): return t[0] == 'OP' and t[1] in group
    def p_or():
        a = p_and()
        while is_op(peek(), OR): nxt(); a = ('or', a, p_and())
        return a
    def p_and():
        a = p_not()
        while True:
            t = peek()
            if is_op(t, AND): nxt(); a = ('and', a, p_not())
            elif t[0] in ('TERM', '(') or is_op(t, NOT): a = ('and', a, p_not())
            else: return a
    def p_not():
        if is_op(peek(), NOT): nxt(); return ('not', p_not())
        return p_atom()
    def p_atom():
        t = nxt()
        if t[0] is None: raise FilterError('表达式不完整：运算符后面缺少条件')
        if t[0] == '(':
            a = p_or()
            if nxt()[0] != ')': raise FilterError('括号不匹配：缺少右括号 )')
            return a
        if t[0] == ')': raise FilterError('括号不匹配：多了右括号 ) 或括号内为空')
        if t[0] == 'OP': raise FilterError(f'运算符「{t[1]}」前面缺少条件')
        return term(t[1])
    a = p_or()
    if pos[0] < len(toks): raise FilterError(f'多余的内容：{toks[pos[0]][1]}')
    return a

FIELDS = {'lang', 'user', 'likes', 'is_reply', 'reply', 'platform', 'plat', 'region'}
def term(w):
    m = re.fullmatch(r'(\w+)\s*(>=|<=|!=|>|<|=|:)\s*(.+)', w)
    if m and m.group(1).lower() in FIELDS:
        f, op, v = m.group(1).lower(), m.group(2), m.group(3)
        f = {'reply': 'is_reply', 'plat': 'platform'}.get(f, f)
        if f in ('likes', 'is_reply'):
            if not re.fullmatch(r'\d+', v): raise FilterError(f'「{f}」后面需要数字：{w}')
            v = int(v)
        elif op not in (':', '=', '!='): raise FilterError(f'「{f}」只能用 : 或 = ：{w}')
        return ('field', f, op, v)
    if m and op_like(w) and m.group(1).lower() not in FIELDS and ':' in w and not w.lower().startswith('http'):
        raise FilterError(f'未知字段「{m.group(1)}」，可用：lang / user / likes / is_reply / platform / region')
    return ('term', w)
def op_like(w): return re.fullmatch(r'[A-Za-z_]+:.+', w) is not None

def _match_term(t, text_l):
    t = t.lower()
    if re.fullmatch(r'[a-z0-9]+', t): return re.search(r'(?<![a-z0-9])' + re.escape(t), text_l) is not None   # word-start match
    return t in text_l
def _cmp(a, op, b):
    return {'>': a > b, '<': a < b, '>=': a >= b, '<=': a <= b, '=': a == b, ':': a == b, '!=': a != b}[op]
def evaluate(ast, c):
    """c: dict with text, lang, commenter, likes, is_reply, platform, region"""
    if ast is None: return True
    k = ast[0]
    if k == 'and': return evaluate(ast[1], c) and evaluate(ast[2], c)
    if k == 'or': return evaluate(ast[1], c) or evaluate(ast[2], c)
    if k == 'not': return not evaluate(ast[1], c)
    if k == 'term': return _match_term(ast[1], (c.get('text') or '').lower())
    _, f, op, v = ast
    if f == 'likes': return _cmp(int(c.get('likes') or 0), op, v)
    if f == 'is_reply': return _cmp(int(c.get('is_reply') or 0), op, v)
    val = str({'lang': c.get('lang'), 'user': c.get('commenter'), 'platform': c.get('platform'), 'region': c.get('region')}[f] or '').lower()
    v = str(v).lower()
    if f in ('user', 'region'): r = v in val
    elif f == 'platform': r = val.startswith(v)
    else: r = val == v
    return (not r) if op == '!=' else r
def compile_filter(s):
    ast = parse(s); return lambda c: evaluate(ast, c)
