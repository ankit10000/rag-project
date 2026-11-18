"""Matching normalization and boundary matching, WP5 §4."""
import re
import unicodedata
from . import tables as T


def light(text, *, casefold=True):
    if not isinstance(text, str):
        raise ValueError('text must be a string')
    # Preserve closed quote mappings whose identity NFKC would destroy (″).
    text = unicodedata.normalize('NFKC', text.translate(str.maketrans(T.QUOTES)))
    if casefold:
        text = text.casefold()
    text = text.translate(str.maketrans(T.QUOTES | T.DASHES))
    text = re.sub('[\u200b\ufeff]', '', text)
    text = re.sub('[\u00a0\u2007\u2009\u202f\u200a\t]', ' ', text)
    text = re.sub(T.REF_PATTERN, '', text, flags=re.I).replace('*', '').replace('`', '')
    return re.sub(r'(?<=[\d:])\s*-\s*(?=\d)', '-', text)


def canon_decimal(n):
    n = str(n)
    return n.rstrip('0').rstrip('.') if '.' in n else n


def time_value(m):
    h, minute = int(m['h']), m['m'] or '00'
    if 'ap' in m.re.groupindex:
        h = h % 12 + (12 if m['ap'].startswith('p') else 0)
    return f'{h:02}:{minute}'


_UNIT = '|'.join(re.escape(x) for x in sorted(T.UNIT_LOOKUP, key=len, reverse=True))
_N = r'(?<![\w.−])-?\d+(?:\.\d+)?'


def _words(text):
    words = list(re.finditer(r'\b[a-z]+\b', text))
    replacements = []
    blocked = set(T.NUMBER_WORDS) | T.SCALE_WORDS
    i = 0
    while i < len(words):
        w = words[i]; value = T.NUMBER_WORDS.get(w.group())
        end, last = w.end(), i
        if value is None:
            i += 1; continue
        if value >= 20 and value % 10 == 0 and i + 1 < len(words):
            nxt = words[i+1]
            if T.NUMBER_WORDS.get(nxt.group(), 0) in range(2, 10) and re.fullmatch(r'[ -]', text[end:nxt.start()]):
                value += T.NUMBER_WORDS[nxt.group()]; end = nxt.end(); last = i+1
        adjacent = False
        for pos, left, right in ((i-1, None, w.start()), (last+1, end, None)):
            if 0 <= pos < len(words) and words[pos].group() == 'and':
                pos += -1 if left is None else 1
            if 0 <= pos < len(words) and words[pos].group() in blocked:
                gap = text[words[pos].end():right] if left is None else text[left:words[pos].start()]
                adjacent |= bool(re.fullmatch(r'(?:[ -]|\s+and\s+)+', gap))
        if not adjacent:
            replacements.append((w.start(), end, str(value)))
        i = last + 1
    for a,b,value in reversed(replacements):
        text = text[:a] + value + text[b:]
    return text


def _quantities(text):
    for iso, aliases in T.CURRENCY.items():
        prefix = '|'.join(re.escape(x) for x in aliases if x in ('usd','us$','$','gbp','£','eur','€'))
        suffix = '|'.join(re.escape(x) for x in sorted(aliases, key=len, reverse=True) if x not in ('$','us$','£','€'))
        text = re.sub(r'(?<!\w)(?:'+prefix+r')\s?(-?\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?',
                      lambda m: iso+' '+canon_decimal(m[1]) + ('-'+iso+' '+canon_decimal(m[2]) if m[2] else ''), text)
        text = re.sub('('+_N+r')\s?(?:'+suffix+r')\b', lambda m: iso+' '+canon_decimal(m[1]), text)
    text = re.sub('('+_N+r')\s?(?:%|percent\b|per cent\b)', lambda m: canon_decimal(m[1])+'%', text)
    text = re.sub('('+_N+r')(?:\s?|-)(?P<u>'+_UNIT+r')\b', lambda m: canon_decimal(m[1])+' '+T.UNIT_LOOKUP[m['u']], text)
    return text


def M(text):
    text = light(text)
    text = text.replace('×', ' x ')
    text = re.sub(r'(\d)\s*x\s*(\d)', r'\1 x \2', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*(mm|cm|m|km|in|ft)?\s+by\s+(\d+(?:\.\d+)?)\s*(mm|cm|m|km|in|ft)\b', lambda m: m[1]+(' '+m[2] if m[2] else '')+' x '+m[3]+' '+m[4], text)
    text = re.sub(r'(?<![\d.,])(\d{1,3}(?:,\d{3})+)(?![\d]|[.,]\d)', lambda m: m[1].replace(',', ''), text)
    text = re.sub(T.TIME12, time_value, text)
    text = re.sub(T.TIME24, time_value, text)
    text = _quantities(text)
    text = _quantities(_words(text))
    return re.sub(r'\s+', ' ', text).strip()


def occurrences(h, n):
    if not n:
        return []
    needles = {n}
    q = re.fullmatch(r'(-?\d+(?:\.\d+)?) ([a-z]+)', n)
    if q:
        word = q[2]
        needles |= {q[1]+' '+word+'s', q[1]+' '+word+'es'}
        if word.endswith('s'):
            needles.add(q[1]+' '+word[:-1])
    spans = set()
    for needle in needles:
        start = 0
        while (i := h.find(needle, start)) >= 0:
            j = i+len(needle); start = i+1
            L = h[i-1] if i else ''; LL = h[i-2] if i > 1 else ''
            R = h[j] if j < len(h) else ''; RR = h[j+1] if j+1 < len(h) else ''
            if needle[0].isalnum() and L.isalnum(): continue
            if needle[0].isdigit() and ((L in ('.',',',':') and LL.isdigit()) or L == '−' or (L == '-' and not LL.isdigit())): continue
            if needle[-1].isalnum() and R.isalnum(): continue
            if needle[-1].isdigit() and R in ('.',',',':') and RR.isdigit(): continue
            spans.add((i,j))
    return sorted(spans)


def contains(h, n):
    return bool(occurrences(h, n))
