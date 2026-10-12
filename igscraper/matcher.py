import re
DEFAULT_INQ = r"\b(how much|price|pricing|cost|precio|preço|prix|rate|moq|minimum|wholesale|bulk|catalog(ue)?|custom|oem|logo|ship|shipping|deliver|whats ?app|wechat|contact|order|buy|purchase|where|located|sample)\b"
DEFAULT_SPAM = r"(follow (me|us)|check (my|our) (page|profile|bio)|we (are|can|offer|produce|make|manufacture|provide)|our (factory|company|brand|products?)|promot|link in (my )?bio|looking for (premium|a reliable|high)|i can (help|handle|source)|sourcing agent|scam|\+?\d{9,})"
class Matcher:
    def __init__(self, phrases=(), use_default=True, question_mark=True):
        self.inq = re.compile(DEFAULT_INQ, re.I) if use_default else None
        ph = [p.strip().lower() for p in phrases if p and p.strip()]
        self.ph = ph
        self.spam = re.compile(DEFAULT_SPAM, re.I); self.qm = question_mark
    def is_q(self, text, user, owner):
        tl = (text or '').lower()
        if user == owner or len(tl) < 3 or self.spam.search(tl): return False
        t2 = re.sub(r'@[\w.]+', '', tl).strip()
        if self.inq and self.inq.search(t2): return True
        for p in self.ph:
            if re.fullmatch(r'[a-z0-9 \'-]+', p):
                if re.search(r'\b' + re.escape(p) + r'\b', t2): return True
            elif p in t2: return True   # CJK etc: substring
        return self.qm and ('?' in t2 or '？' in t2) and len(t2) > 6
